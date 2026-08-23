# Fabric notebook source
# METADATA ********************
# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {}
# META }

# CELL ********************

from pyspark.sql import functions as F

table_names = [
    "customers",
    "products",
    "subscriptions",
    "invoices",
    "payments",
    "usage_monthly",
    "support_cases",
    "cloud_costs",
    "renewal_forecasts",
    "customer_finance_summary",
]

double_columns = {
    "list_price_arr", "arr", "amount", "adoption_rate", "compute_hours", "support_hours",
    "compute_cost", "storage_cost", "support_cost", "total_cost", "renewal_arr",
    "renewal_probability", "mrr", "billed_revenue_6m", "cash_collected_6m",
    "ar_outstanding", "overdue_ar", "cost_6m", "gross_margin_pct",
    "latest_adoption_rate", "usage_trend_pct",
}
integer_columns = {"licensed_users", "active_users", "production_jobs", "open_critical_cases"}
date_columns = {
    "start_date", "renewal_date", "invoice_date", "due_date", "paid_date",
    "payment_date", "usage_month", "opened_date", "resolved_date", "cost_month",
}

results = []
for table_name in table_names:
    frame = (
        spark.read.option("header", True)
        .option("nullValue", "")
        .csv(f"Files/raw/{table_name}.csv")
    )
    for column in frame.columns:
        if column in double_columns:
            frame = frame.withColumn(column, F.col(column).cast("double"))
        elif column in integer_columns:
            frame = frame.withColumn(column, F.col(column).cast("long"))
        elif column in date_columns:
            frame = frame.withColumn(column, F.to_timestamp(column, "yyyy-MM-dd"))
    (
        frame.write.mode("overwrite")
        .option("overwriteSchema", "true")
        .format("delta")
        .saveAsTable(table_name)
    )
    results.append({"table": table_name, "rows": frame.count()})

display(spark.createDataFrame(results))
