# Retail sales model specification

A complete spec. dim_check.py must report nothing at all against this.

## Fact: fact_sales_line

**Grain**: one row represents one line item on one point-of-sale transaction at one
store.

**Type**: transaction

**Foreign keys**:
- date_key (role: transaction date)
- customer_key
- product_key
- order_number (degenerate dimension)

**Measures**:

| Name | Data type | Additivity | Definition |
|---|---|---|---|
| quantity_sold | int | additive | Units sold on this line |
| extended_amount | decimal(18,2) | additive | Quantity multiplied by unit price |
| discount_amount | decimal(18,2) | additive | Discount applied to this line |

**Source**: point-of-sale transaction log

**Update pattern**: append-only

**Owner**: retail analytics

## Dimension: dim_customer

**Business meaning**: one row represents one version of one purchasing customer.

**Natural key**: customer_id from the CRM

**Surrogate key**: customer_key

**Durable key**: customer_durable_key

**SCD type**: 2

**Attributes**:

| Name | SCD behavior | Source |
|---|---|---|
| customer_name | type 1 | CRM |
| customer_segment | inherits | CRM |
| city_name | inherits | CRM |

**Hierarchies**: city to state, fixed depth

**Conformance scope**: fact_sales_line, fact_returns

**Unknown member**: customer_key 0, labelled "Unknown customer"

**Owner**: customer data steward
