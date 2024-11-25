# Copyright 2024 Jarsa (https://www.jarsa.com)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models


class AccountPartialReconcile(models.Model):
    _inherit = "account.partial.reconcile"

    def _create_tax_cash_basis_moves(self):
        moves = super()._create_tax_cash_basis_moves()
        rec = self[0]
        date = rec.max_date
        if rec.debit_move_id.journal_id.type in ["bank", "cash"]:
            date = rec.debit_move_id.date
        elif rec.credit_move_id.journal_id.type in ["bank", "cash"]:
            date = rec.credit_move_id.date
        vals = {"date": date}
        moves.write(vals)
        if date.month != rec.max_date.month:
            moves._compute_name()
        return moves
