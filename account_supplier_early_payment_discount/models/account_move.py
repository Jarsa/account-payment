# Copyright 2026 Jarsa
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = "account.move"

    early_payment_date = fields.Date(
        compute="_compute_early_payment",
        store=True,
        help="Last day to pay to earn the early payment discount of the "
        "supplier, counted from the invoice or from the receipt as its "
        "conditions say.",
    )
    early_payment_amount = fields.Monetary(
        compute="_compute_early_payment",
        store=True,
        help="What the early payment discount of the supplier takes off this bill.",
    )
    early_payment_credit_note_id = fields.Many2one(
        "account.move",
        readonly=True,
        copy=False,
        help="Credit note applied to this bill for the early payment discount. "
        "The supplier still owes its own credit note; an activity follows it up.",
    )

    @api.depends(
        "move_type",
        "invoice_date",
        "amount_total",
        "partner_id.commercial_partner_id.early_payment_percent",
        "partner_id.commercial_partner_id.early_payment_percent_2",
        "partner_id.commercial_partner_id.early_payment_days",
        "partner_id.commercial_partner_id.early_payment_base",
        "invoice_line_ids.purchase_line_id.order_id.picking_ids.date_done",
    )
    def _compute_early_payment(self):
        for move in self:
            partner = move.partner_id.commercial_partner_id
            ratio = partner._early_payment_ratio() if partner else 0.0
            base = (
                move._early_payment_base_date()
                if move.move_type == "in_invoice" and ratio > 0
                else False
            )
            move.early_payment_date = (
                base + timedelta(days=partner.early_payment_days) if base else False
            )
            move.early_payment_amount = (
                move.currency_id.round(move.amount_total * ratio) if base else 0.0
            )

    def _early_payment_base_date(self):
        """Day the early payment days count from: the receipt when the
        supplier says so and the goods are in, the invoice otherwise."""
        self.ensure_one()
        if self.partner_id.commercial_partner_id.early_payment_base == "receipt":
            pickings = (
                self.invoice_line_ids.purchase_line_id.order_id.picking_ids.filtered(
                    lambda picking: picking.state == "done"
                    and picking.picking_type_code == "incoming"
                )
            )
            if pickings:
                return max(pickings.mapped("date_done")).date()
        return self.invoice_date

    def _early_payment_pay_date(self):
        """Business day the early payment is paid on.

        The early payment date itself, or the business day before it when it
        falls on a weekend or a holiday: paying after it loses the discount.
        """
        self.ensure_one()
        date = self.early_payment_date
        if not date:
            return False
        company = self.company_id
        return (
            date
            if company._is_business_day(date)
            else company._add_business_days(date, -1)
        )

    def _early_payment_applies_on(self, date):
        """Whether paying on `date` earns the discount, and it is not taken yet."""
        self.ensure_one()
        return bool(
            self.move_type == "in_invoice"
            and self.state == "posted"
            and self.early_payment_date
            and date <= self.early_payment_date
            and self.early_payment_amount > 0
            and not self.early_payment_credit_note_id
        )

    def action_apply_early_payment(self):
        """Take the early payment discount off the bill.

        A credit note for the discount is posted and reconciled with the
        bill, so what is left to pay is the discounted amount. It stands for
        the credit note the supplier owes, which an activity on it follows
        up, so the credit notes suppliers owe are never lost track of.
        """
        self.ensure_one()
        if self.move_type != "in_invoice" or self.state != "posted":
            raise UserError(
                self.env._(
                    "The early payment discount applies to posted vendor bills only."
                )
            )
        if self.early_payment_credit_note_id:
            raise UserError(
                self.env._(
                    "The early payment discount of %s is already taken.",
                    self.early_payment_credit_note_id.name,
                )
            )
        partner = self.partner_id.commercial_partner_id
        ratio = partner._early_payment_ratio()
        if ratio <= 0:
            raise UserError(
                self.env._("%s has no early payment discount.", partner.display_name)
            )
        today = fields.Date.context_today(self)
        credit_note = self._reverse_moves(
            [
                {
                    "invoice_date": today,
                    "date": today,
                    "ref": self.env._("Early payment discount of %s", self.name),
                }
            ]
        )
        for line in credit_note.invoice_line_ids:
            line.price_unit = line.price_unit * ratio
        credit_note.action_post()
        (self.line_ids + credit_note.line_ids).filtered(
            lambda line: line.account_id.account_type == "liability_payable"
            and not line.reconciled
        ).reconcile()
        self.early_payment_credit_note_id = credit_note
        credit_note.activity_schedule(
            "mail.mail_activity_data_todo",
            summary=self.env._("Early payment credit note pending"),
            note=self.env._(
                "%(supplier)s owes a credit note for %(amount)s of early payment "
                "discount on %(bill)s, taken with this internal credit note. When "
                "its credit note arrives, attach it here and close this activity.",
                supplier=partner.display_name,
                amount=credit_note.amount_total,
                bill=self.name,
            ),
            **self._early_payment_activity_assignee(),
        )
        return credit_note

    def _early_payment_activity_assignee(self):
        """Who chases the credit note: the follow-up team, as a whole.

        The users of the follow-up group make the members of the activity
        team, so the to-do shows to every one of them and any of them closes
        it. Without users in the group it falls back to the buyer of the
        supplier, so the credit note is never left without an owner.
        """
        self.ensure_one()
        group = self.env.ref(
            "account_supplier_early_payment_discount.account_move_group_early_payment_credit_note"
        )
        team = self.env.ref(
            "account_supplier_early_payment_discount.mail_activity_team_early_payment_credit_note"
        ).sudo()
        team.member_ids = group.user_ids
        if team.member_ids:
            return {"team_id": team.id, "user_id": False}
        partner = self.partner_id.commercial_partner_id
        return {
            "user_id": (partner.buyer_id or self.invoice_user_id or self.env.user).id
        }
