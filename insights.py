
import pandas as pd


def generate_insights(df: pd.DataFrame) -> list[str]:
    """
    Analyze the sales dataframe and return a list of plain-English
    insight strings (e.g. top performer, biggest month, growth trend).
    """
    insights = []

    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    text_cols = df.select_dtypes(include="object").columns.tolist()
    date_cols = [c for c in df.columns if "date" in c.lower()]

    if not numeric_cols:
        insights.append("No numeric columns found, so no numeric insights could be generated.")
        return insights

    main_col = numeric_cols[0]  # assume first numeric column is the main value (e.g. Revenue)

    # ---- Overall totals ----
    total = df[main_col].sum()
    average = df[main_col].mean()
    insights.append(f"Total {main_col}: {total:,.0f}")
    insights.append(f"Average {main_col} per record: {average:,.2f}")

    # ---- Top performing category (e.g. top Sales Rep / Region / Product) ----
    if text_cols:
        group_col = text_cols[0]
        grouped = df.groupby(group_col)[main_col].sum().sort_values(ascending=False)
        if len(grouped) > 0:
            top_name = grouped.index[0]
            top_value = grouped.iloc[0]
            share = (top_value / total * 100) if total else 0
            insights.append(
                f"Top {group_col}: '{top_name}' with {top_value:,.0f} "
                f"({share:.1f}% of total {main_col})."
            )

        if len(grouped) > 1:
            bottom_name = grouped.index[-1]
            bottom_value = grouped.iloc[-1]
            insights.append(
                f"Lowest performing {group_col}: '{bottom_name}' with {bottom_value:,.0f}."
            )

    # ---- Trend over time ----
    if date_cols:
        date_col = date_cols[0]
        df = df.copy()
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        monthly = df.groupby(df[date_col].dt.to_period("M"))[main_col].sum()

        if len(monthly) >= 2:
            last = monthly.iloc[-1]
            prev = monthly.iloc[-2]
            change = last - prev
            pct_change = (change / prev * 100) if prev else 0
            direction = "up" if change > 0 else "down" if change < 0 else "flat"
            insights.append(
                f"Latest month ({monthly.index[-1]}) {main_col} is {direction} "
                f"{abs(pct_change):.1f}% vs previous month "
                f"({prev:,.0f} -> {last:,.0f})."
            )

        best_month = monthly.idxmax()
        best_month_value = monthly.max()
        insights.append(f"Best month so far: {best_month} with {best_month_value:,.0f} {main_col}.")

    # ---- Data quality flags ----
    missing = df.isna().sum()
    cols_with_missing = missing[missing > 0]
    if not cols_with_missing.empty:
        cols_list = ", ".join(cols_with_missing.index.tolist())
        insights.append(f"⚠️ Missing values detected in: {cols_list}. Consider cleaning the source file.")

    return insights