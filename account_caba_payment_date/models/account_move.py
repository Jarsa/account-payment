# Copyright 2026 Jarsa (https://www.jarsa.com)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from markupsafe import Markup

from odoo import _, models
from odoo.tools import format_date


class AccountMove(models.Model):
    _inherit = "account.move"

    def _log_cash_basis_lock_shift(self, expected_date_per_partial):
        """Post a traceability message on the cash basis entry and its source
        documents when the entry date differs from the date of the source
        documents because their period was closed.

        :param expected_date_per_partial: mapping of ``account.partial.reconcile``
            id to the originally expected date (the date the entry would have
            used if the period were open). Only the partials present in this
            mapping have been shifted.
        """
        # Track (document, expected_date) already messaged to post a single
        # message per source document, even when several cash basis entries
        # share the same partial.
        seen = set()
        for move in self:
            partial = move.tax_cash_basis_rec_id
            expected_date = expected_date_per_partial.get(partial.id)
            if not expected_date or move.date == expected_date:
                continue
            body = Markup(
                _(
                    "The VAT cash basis journal entry was generated with a date "
                    "different from the source documents because the accounting "
                    "period of the expected date was closed."
                    "<br/>Expected date: %(expected)s"
                    "<br/>Applied date: %(applied)s"
                )
            ) % {
                "expected": format_date(self.env, expected_date),
                "applied": format_date(self.env, move.date),
            }
            # The cash basis entry itself always gets its own message.
            move.message_post(body=body)
            # The source documents get a single message per shifted date.
            source_documents = partial.debit_move_id.move_id | partial.credit_move_id.move_id
            for document in source_documents:
                key = (document.id, expected_date)
                if key in seen:
                    continue
                seen.add(key)
                document.message_post(body=body)
