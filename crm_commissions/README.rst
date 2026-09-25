.. image:: https://odoo-community.org/readme-banner-image
   :target: https://odoo-community.org/get-involved?utm_source=readme
   :alt: Odoo Community Association

====================
CRM Commissions IOMR
====================

.. |badge1| image:: https://img.shields.io/badge/maturity-Beta-yellow.png
    :target: https://odoo-community.org/page/development-status
    :alt: Beta
.. |badge2| image:: https://img.shields.io/badge/license-AGPL--3-blue.png
    :target: http://www.gnu.org/licenses/agpl-3.0-standalone.html
    :alt: License: AGPL-3
.. |badge3| image:: https://img.shields.io/badge/github-IOMR%2Fcrm--commissions-lightgray.png?logo=github
    :target: https://github.com/OCA/commission/tree/18.0/crm_commissions
    :alt: IOMR/crm-commissions

|badge1| |badge2| |badge3|

CRM Commissions module for IOMR healthcare sales management.

This module extends the OCA commission system with:

- Progressive commission rates based on monthly performance vs target
- Orientadora (saleswoman), SDR, Coordenadora, and Doctor profiles
- CRM Health Index (IS-CRM) scoring with bonus/penalty
- Monthly target tracking, including team-wide target distribution
- Automatic quarterly bonus records generated from monthly targets
- Automatic quarter closing and recovery of lost base-rate points
- Individual and team/coordinator eligibility for the special prize
- Manual special-prize registration, since the policy defines no fixed formula
- Team-based coordinator commissions
- Portal access for doctors to view their opportunities

**Table of contents**

.. contents::
   :local:

Configuration
=============

1. Go to *CRM > Config. Comissão LIOs* to set up progressive commission types.
2. Define the progressive rate bands (performance % range -> commission %).
   The same bands are used to calculate quarterly recovery.
3. Set IS-CRM bonus/penalty percentages and the active policy.
4. Create agent profiles (Orientadora, SDR, Coordenadora) in Contacts and ensure
   each Orientadora has a linked *commission.member* record.
5. Create teams under *CRM Comissões > Equipes* and add their Orientadoras.
6. Set one monthly target per Orientadora under *CRM Comissões > Metas Mensais*.
   Use *Aplicar à Equipe* to distribute a team target.
7. Review the automatically generated records under *CRM Comissões > Bônus
   Trimestrais*. Existing monthly targets are synchronized during upgrade.
8. The scheduled action *CRM Comissões: sincronizar e fechar bônus
   trimestrais* runs daily to refresh totals and close expired quarters.
9. Register the special prize manually after eligibility is confirmed; the
   policy does not define a fixed prize amount.

Usage
=====

1. Orientadoras access Odoo as internal users to manage their leads and sales.
2. Doctors access via portal to view their linked opportunities.
3. The first monthly target creates one pending quarterly bonus. Further
   monthly targets are attached to the same salesperson/quarter record.
4. Confirmed orders refresh achieved amounts, monthly performance, and the
   quarterly total.
5. After the quarter ends, the daily job finalizes it as *Incomplete goals*,
   *Eligible*, *Recovered/Paid*, or *Lost*.
6. If quarterly performance is at least 100%, lost base-rate points from
   underperforming months are recovered. IS-CRM adjustments remain separate.
7. Team/coordinator eligibility is calculated from the aggregate target and
   achievement of the Orientadoras assigned to the sales team.
8. The special prize amount, type, and description are entered manually.

Bug Tracker
===========

Bugs are tracked on GitHub Issues. In case of trouble, please check there if your issue has already been reported.

Credits
=======

Authors
-------

* IOMR

Contributors
------------

- IOMR - Rodrigo <rodrigo@iomr.com.br>

Maintainers
-----------

This module is maintained by the OCA.

.. image:: https://odoo-community.org/logo.png
   :alt: Odoo Community Association
   :target: https://odoo-community.org

OCA, or the Odoo Community Association, is a nonprofit organization whose mission is to support the collaborative development of Odoo features and promote its widespread use.

This module is part of the IOMR/crm-commissions project on GitHub.
