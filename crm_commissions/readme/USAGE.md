1. Orientadoras access Odoo as internal users to manage leads and sales;
   Doctors use the portal to view their linked opportunities.
2. Register the monthly target for each Orientadora. The target date is
   normalized to the first day of the month, and duplicate salesperson/month
   targets are rejected.
3. The first monthly target automatically creates a *Pending* quarterly bonus
   record. The following monthly targets are attached to the same record and the
   quarterly target is recalculated as their sum.
4. Confirmed or invoiced orders update monthly achievement. Changes to targets
   and orders are synchronized automatically.
5. A quarter is finalized only after its end date. The daily scheduled action
   evaluates it; managers may also use *Atualizar e finalizar trimestre* once
   the quarter is closed.
6. Final states are:
   - *Incomplete goals*: the quarter closed without all three monthly goals;
   - *Eligible*: the quarter reached 100% and no rate points require recovery;
   - *Recovered/Paid*: the quarter reached 100% and lost base-rate points were
     recovered;
   - *Lost*: the quarter remained below 100%.
7. Recovery is calculated only for eligible quarters. For each month below
   100%, the system restores the difference between the policy rate at 100% and
   the month's effective base rate, applied to that month's eligible commission
   base. IS-CRM bonus/penalty is evaluated separately and is not cancelled by
   this recovery.
8. Team totals aggregate the Orientadoras assigned to the same sales team.
   *Team/coordinator eligible* confirms whether the collective quarterly goal
   was reached for the coordinator's special prize.
9. The special prize amount, type, and description are maintained manually
   because the policy defines no fixed prize formula.
