# Incomplete model specification

## Fact: fact_orders

**Foreign keys**:
- date_key
- customer_key

**Measures**:

| Name | Data type | Additivity | Definition |
|---|---|---|---|
| order_amount | decimal(18,2) | | Value of the order |
| margin_pct | decimal(9,4) | non-additive | Margin percentage |

**Source**: order management system

## Fact: fact_shipments

**Grain**: one row per shipment, or per shipment line for international orders.

**Type**: transaction

**Measures**:

| Name | Data type | Additivity | Definition |
|---|---|---|---|
| shipped_quantity | int | additive | Units shipped |

## Dimension: dim_employee

**Business meaning**: one row represents one employee.

**Natural key**: employee_number

**Attributes**:

| Name | SCD behavior | Source |
|---|---|---|
| employee_name | inherits | HR |

## Dimension: dim_supplier

**Business meaning**: one row represents one version of one supplier.

**SCD type**: 2

**Attributes**:

| Name | SCD behavior | Source |
|---|---|---|
| supplier_name | inherits | ERP |
