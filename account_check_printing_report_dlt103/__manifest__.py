# Copyright 2023 ForgeFlow S.L.
# © 2018 Serpent Consulting Services Pvt. Ltd.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

{
    "name": "Account Check Printing Report DLT103",
    "version": "15.0.1.0.0",
    "license": "AGPL-3",
    "author": "ForgeFlow,"
    "Serpent Consulting Services Pvt. Ltd.,"
    "Odoo Community Association (OCA)",
    "category": "Generic Modules/Accounting",
    "website": "https://github.com/OCA/account-payment",
    "depends": ["account_check_printing_report_base"],
    "data": [
        "data/report_paperformat.xml",
        "data/report_paperformat_parameter.xml",
        "views/report_check_dlt103.xml",
        "report/account_check_writing_report.xml",
    ],
    "installable": True,
}
