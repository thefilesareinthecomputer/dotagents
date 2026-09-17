-- A correct star schema. dim_check.py must report nothing at all against this.

CREATE TABLE dim_date (
    date_key            INT          NOT NULL PRIMARY KEY,  -- YYYYMMDD
    full_date           DATE         NOT NULL,
    day_name            VARCHAR(10)  NOT NULL,
    month_name          VARCHAR(10)  NOT NULL,
    fiscal_period_name  VARCHAR(20)  NOT NULL,
    is_national_holiday VARCHAR(3)   NOT NULL
);

CREATE TABLE dim_customer (
    customer_key        INT          NOT NULL PRIMARY KEY,
    customer_durable_key INT         NOT NULL,
    customer_id         VARCHAR(20)  NOT NULL,
    customer_name       VARCHAR(120) NOT NULL,
    customer_segment    VARCHAR(40)  NOT NULL,
    city_name           VARCHAR(60)  NOT NULL,
    state_name          VARCHAR(60)  NOT NULL,
    effective_from      TIMESTAMP    NOT NULL,
    effective_to        TIMESTAMP    NOT NULL,
    is_current          CHAR(1)      NOT NULL
);

CREATE TABLE dim_product (
    product_key         INT          NOT NULL PRIMARY KEY,
    product_id          VARCHAR(20)  NOT NULL,
    product_name        VARCHAR(120) NOT NULL,
    brand_name          VARCHAR(60)  NOT NULL,
    category_name       VARCHAR(60)  NOT NULL,
    department_name     VARCHAR(60)  NOT NULL
);

CREATE TABLE fact_sales_line (
    sales_line_key      BIGINT       NOT NULL,
    date_key            INT          NOT NULL,
    customer_key        INT          NOT NULL,
    product_key         INT          NOT NULL,
    order_number        VARCHAR(20)  NOT NULL,   -- degenerate dimension
    quantity_sold       INT          NOT NULL,
    extended_amount     DECIMAL(18,2) NOT NULL,
    discount_amount     DECIMAL(18,2) NOT NULL,
    PRIMARY KEY (sales_line_key)
);
