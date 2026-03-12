import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import plotly.express as px

st.set_page_config(page_title="Order Manager", layout="wide")

st.title("Order Management")

# -------------------------
# CONNECT GOOGLE SHEETS
# -------------------------

scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=scope
)

client = gspread.authorize(creds)

sheet = client.open("Order Management")

products_sheet = sheet.worksheet("Products")
customers_sheet = sheet.worksheet("Customers")
orders_sheet = sheet.worksheet("Orders")


# -------------------------
# LOAD DATA (CACHED)
# -------------------------

@st.cache_data(ttl=600)
def load_products():
    return products_sheet.get_all_records()

@st.cache_data(ttl=600)
def load_customers():
    return customers_sheet.get_all_records()

@st.cache_data(ttl=600)
def load_orders():
    return orders_sheet.get_all_records()


products = load_products()
customers = load_customers()
orders = load_orders()

df_products = pd.DataFrame(products)
df_customers = pd.DataFrame(customers)
df_orders = pd.DataFrame(orders)

# -------------------------
# MAPS
# -------------------------

product_map = {}
customer_map = {}

product_list = []
customer_list = []

if not df_products.empty:
    product_map = {p["Product_Name"]: p for p in products}
    product_list = sorted(product_map.keys())

if not df_customers.empty:
    customer_map = {c["Customer_Name"]: c for c in customers}
    customer_list = sorted(customer_map.keys())


# -------------------------
# MERGE DATA
# -------------------------

df = pd.DataFrame()

if not df_orders.empty:

    df = df_orders.merge(df_customers, on="Customer_ID", how="left")
    df = df.merge(df_products, on="Product_ID", how="left")


# -------------------------
# TABS
# -------------------------

tab1, tab2 = st.tabs(["Dashboard", "Orders"])


# =====================================================
# DASHBOARD
# =====================================================

with tab1:

    st.header("Dashboard")

    if df.empty:

        st.info("No orders yet")

    else:

        active_orders = df[df["Status"] == "Active"]

        # -------------------------
        # PIE CHART
        # -------------------------

        if not active_orders.empty:

            st.subheader("Orders by Direction")

            direction_counts = (
                active_orders["Direction"]
                .value_counts()
                .reset_index()
            )

            direction_counts.columns = ["Direction", "Orders"]

            fig = px.pie(
                direction_counts,
                names="Direction",
                values="Orders",
                hole=0.4
            )

            st.plotly_chart(fig, use_container_width=True)

        # -------------------------
        # FILTERS
        # -------------------------

        st.subheader("Filters")

        col1, col2, col3 = st.columns(3)

        with col1:
            product_filter = st.selectbox(
                "Product",
                ["All"] + sorted(active_orders["Product_Name"].dropna().unique())
            )

        with col2:
            customer_filter = st.selectbox(
                "Customer",
                ["All"] + sorted(active_orders["Customer_Name"].dropna().unique())
            )

        with col3:
            direction_filter = st.selectbox(
                "Direction",
                ["All"] + sorted(active_orders["Direction"].dropna().unique())
            )

        filtered = active_orders.copy()

        if product_filter != "All":
            filtered = filtered[filtered["Product_Name"] == product_filter]

        if customer_filter != "All":
            filtered = filtered[filtered["Customer_Name"] == customer_filter]

        if direction_filter != "All":
            filtered = filtered[filtered["Direction"] == direction_filter]

        # -------------------------
        # ACTIVE ORDERS TABLE
        # -------------------------

        st.subheader("Active Orders")

        if filtered.empty:

            st.write("No matching orders")

        else:

            display_df = filtered[
                [
                    "Order_ID",
                    "Product_Name",
                    "Quantity",
                    "Customer_Name",
                    "Address",
                    "Direction"
                ]
            ].reset_index(drop=True)

            display_df["Done"] = False

            edited = st.data_editor(
                display_df,
                use_container_width=True,
                hide_index=True
            )

            done_rows = edited[edited["Done"] == True]

            if st.button("Mark Selected as Done"):

                done_ids = done_rows["Order_ID"].tolist()

                sheet_rows = orders_sheet.get_all_records()

                for i, row in enumerate(sheet_rows, start=2):

                    if row["Order_ID"] in done_ids:

                        orders_sheet.update_cell(i, 8, "Done")

                st.success("Orders updated")

                st.cache_data.clear()
                st.rerun()


# =====================================================
# ORDER ENTRY
# =====================================================

with tab2:

    st.header("Add Order")

    if not customer_list or not product_list:

        st.warning("Products or Customers sheet is empty")

    else:

        customer_name = st.selectbox(
            "Customer",
            customer_list
        )

        if "order_items" not in st.session_state:
            st.session_state.order_items = []

        product_name = st.selectbox(
            "Product",
            product_list
        )

        quantity = st.number_input(
            "Quantity",
            min_value=1
        )

        if st.button("Add Product"):

            st.session_state.order_items.append(
                {
                    "product": product_name,
                    "quantity": quantity
                }
            )

        st.subheader("Current Order")

        for i, item in enumerate(st.session_state.order_items):

            col1, col2, col3 = st.columns([5,2,1])

            col1.write(item["product"])
            col2.write(f"Qty: {item['quantity']}")

            if col3.button("❌", key=f"remove_{i}"):

                st.session_state.order_items.pop(i)
                st.rerun()

        notes = st.text_input("Notes")

        if st.button("Place Order"):

            if not st.session_state.order_items:

                st.warning("Add at least one product")

            else:

                customer = customer_map[customer_name]

                today = datetime.today().strftime("%Y-%m-%d")

                existing_orders = orders_sheet.get_all_records()

                order_id = f"O{len(existing_orders)+1:05d}"

                for item in st.session_state.order_items:

                    product = product_map[item["product"]]

                    price = float(product["Price with Tax"])

                    qty = item["quantity"]

                    total = price * qty

                    orders_sheet.append_row([
                        order_id,
                        today,
                        customer["Customer_ID"],
                        product["Product_ID"],
                        qty,
                        price,
                        total,
                        "Active",
                        notes
                    ])

                st.session_state.order_items = []

                st.success("Order created")

                st.cache_data.clear()

                st.rerun()
