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
- Monthly target tracking
- Quarterly bonus and commission recovery
- Team-based coordinator commissions
- Portal access for doctors to view their opportunities

**Table of contents**

.. contents::
   :local:

Configuration
=============

1. Go to *CRM > Config. Comissão LIOs* to set up progressive commission types.
2. Define the progressive rate bands (performance % range -> commission %).
3. Set IS-CRM bonus/penalty percentages.
4. Create agent profiles (Orientadora, SDR, Coordenadora) in Contacts.
5. Set monthly targets under *CRM Comissões > Metas Mensais*.
6. Create teams under *CRM Comissões > Equipes*.

Usage
=====

1. Orientadoras access Odoo as internal users to manage their leads and sales.
2. Doctors access via portal to view their linked opportunities.
3. Monthly targets are set per orientadora.
4. IS-CRM score is evaluated monthly - scores below 95% incur a penalty.
5. Commission is calculated progressively based on % of target achieved.
6. Quarterly bonuses are computed when quarterly targets are met.
7. Coordinator commissions are based on team aggregate performance.

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
