# Copyright 2026 Jarsa (https://www.jarsa.com)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from datetime import date

from markupsafe import Markup

from odoo import _, fields, models
from odoo.tools import format_date

# Private key used to carry the "expected date" of a shifted exchange
# difference entry between the value preparation and the move creation.
SHIFT_KEY = "cash_basis_lock_shift"


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def _prepare_exchange_difference_move_vals(self, amounts_list, company=None, exchange_date=None, **kwargs):
        """Shift the exchange difference (CABA) entry to the operation date when
        its computed date falls in a closed period.

        This mirrors the criterion applied to the cash basis entry: when the
        period of the source documents is closed (fiscal, period or tax lock
        date), the exchange difference inherits the operation date (today)
        instead of being refused at posting.
        """
        vals = super()._prepare_exchange_difference_move_vals(
            amounts_list, company=company, exchange_date=exchange_date, **kwargs
        )
        if not vals or not vals.get("move_values"):
            return vals
        move_values = vals["move_values"]
        move_company = self.company_id[:1] or company
        if not move_company:
            return vals
        lock_date = max(
            move_company.with_context(cash_basis_check_tax_lock=True)._get_user_fiscal_lock_date(),
            date.min,
        )
        expected_date = move_values.get("date")
        if expected_date and expected_date <= lock_date:
            move_values["date"] = fields.Date.context_today(self)
            move_values[SHIFT_KEY] = expected_date
        return vals

    def _create_exchange_difference_moves(self, exchange_diff_values_list):
        """Create the exchange difference entries and trace the date shift.

        The private marker added in ``_prepare_exchange_difference_move_vals`` is
        removed before delegating to the standard create, then a traceability
        message is posted on each entry whose date was shifted.
        """
        expected_dates = []
        for exchange_diff_values in exchange_diff_values_list:
            move_values = (exchange_diff_values or {}).get("move_values") or {}
            expected_dates.append(move_values.pop(SHIFT_KEY, None))

        moves = super()._create_exchange_difference_moves(exchange_diff_values_list)

        for move, expected_date in zip(moves, expected_dates):
            if not expected_date:
                continue
            body = Markup(
                _(
                    "The exchange rate difference journal entry inherited the "
                    "operation date because the accounting period of the "
                    "expected date was closed."
                    "<br/>Expected date: %(expected)s"
                    "<br/>Applied operation date: %(applied)s"
                )
            ) % {
                "expected": format_date(self.env, expected_date),
                "applied": format_date(self.env, move.date),
            }
            move.message_post(body=body)
        return moves
