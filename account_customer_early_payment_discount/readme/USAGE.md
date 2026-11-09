A posted customer invoice with such payment terms shows the last day to pay
and the amount of the discount. Once the customer pays at least the discounted
amount within that day, the invoice shows under the *Early Payment to Apply*
filter and the button *Apply Early Payment* appears. Press it: a draft credit
note for the discount is created, with the eligible lines only and their
taxes. Post it (after the approvals of your company, if any) and it is
reconciled with the invoice, which is then fully paid.

Whether an invoice is paid in time is decided by
`account.move._early_payment_paid_on_time()`, and the lines the discount takes
off by `account.move._early_payment_line_eligible()`; both can be overridden.

The days to pay within count from the invoice date, as returned by
`account.move._get_early_payment_date_ref()`. Override it to count them from
another event, such as the day the customer receives the goods, and add the
fields it reads to the dependencies of `_compute_early_payment`.
