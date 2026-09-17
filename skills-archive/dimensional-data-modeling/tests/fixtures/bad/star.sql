-- Every mechanical violation the checker knows about. Must FAIL.

CREATE TABLE fact_sales (
    sale_id         VARCHAR(20),        -- natural key left in the fact table
    date_key        INT NOT NULL,
    month_key       INT NOT NULL,       -- centipede: date hierarchy level
    year_key        INT NOT NULL,       -- centipede: date hierarchy level
    customer_key    INT,                -- nullable foreign key
    product_key     INT NOT NULL,
    customer_name   VARCHAR(100),       -- descriptive attribute in a fact table
    status_code     CHAR(2),            -- descriptive attribute in a fact table
    sales_amount    FLOAT,              -- money as float
    quantity        INT
);

CREATE TABLE dim_customer (
    customer_id     INT NOT NULL PRIMARY KEY,  -- type 2 keyed on the business key
    customer_name   VARCHAR(100),
    customer_city   VARCHAR(60),
    effective_from  DATE,
    is_current      CHAR(1),
    region_key      INT                        -- snowflake onto dim_region
);

CREATE TABLE dim_region (
    region_key      INT NOT NULL PRIMARY KEY,
    region_name     VARCHAR(50),
    country_name    VARCHAR(50),
    continent_name  VARCHAR(50)
);

CREATE TABLE dim_store (
    store_id        INT NOT NULL,               -- no primary key declared
    store_name      VARCHAR(60),
    store_city      VARCHAR(60),
    store_region    VARCHAR(60),
    valid_from      DATE                        -- type 2 housekeeping incomplete
);
