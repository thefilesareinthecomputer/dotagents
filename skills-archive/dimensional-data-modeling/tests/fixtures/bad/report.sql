-- Joining two fact tables on their foreign keys. Must FAIL.

SELECT c.customer_name,
       SUM(s.sales_amount) AS sales,
       SUM(r.return_amount) AS returns
FROM fact_sales s
JOIN fact_returns r
  ON r.customer_key = s.customer_key
 AND r.product_key = s.product_key
JOIN dim_customer c
  ON c.customer_key = s.customer_key
GROUP BY c.customer_name;

-- Legitimate: two facts in separate UNION branches are not a fact-to-fact join.
SELECT customer_key, sales_amount AS amount FROM fact_sales
UNION ALL
SELECT customer_key, -return_amount AS amount FROM fact_returns;
