# -*- coding: utf-8 -*-
################################################################################
#
#    Madooit IT Solutions.
#
#    Copyright (C) 2026-TODAY https://www.madooit.com>).
#    Author:  Rodrigo A. Madureira (rodrigo@madooit.com)
#
#    You can modify it under the terms of the GNU AFFERO
#    GENERAL PUBLIC LICENSE (AGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU AFFERO GENERAL PUBLIC LICENSE (AGPL v3) for more details.
#
#    You should have received a copy of the GNU AFFERO GENERAL PUBLIC LICENSE
#    (AGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
################################################################################
{
    'name': "CRM IOMR Automations",
    'version': '18.0.1.0.0',
    'category': 'Extra Tools',
    'summary': """Custom triggers to CRM""",
    'description': """Custom triggers to CRM""",
    'author': 'Rodrigo A. Madureira',
    'company': 'Madooit IT Solutions',
    'maintainer': 'Madooit IT Solutions',
    'website': "https://www.madooit.com",
    'depends': ['crm', 'sale_management','hr'],
    'data': ['views/crm_lead.xml',
             'views/res_partner.xml',
             ],
    #'images': ['static/description/banner.png'],
    'license': 'AGPL-3',
    'installable': True,
    'application': False,
    'auto_install': False,
}
