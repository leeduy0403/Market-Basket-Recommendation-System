import streamlit as st
import requests, os, pathlib, pandas as pd, ast

# Paths
ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
PRODUCTS_CSV = DATA_DIR / "products.csv"
USER_ITEM_CSV = DATA_DIR / "user_item_dl.csv"
RULES_CSV = DATA_DIR / "rules.csv"

# Load data
products_df = pd.read_csv(PRODUCTS_CSV) if PRODUCTS_CSV.exists() else None
user_item_df = pd.read_csv(USER_ITEM_CSV) if USER_ITEM_CSV.exists() else None
rules_df = pd.read_csv(RULES_CSV) if RULES_CSV.exists() else None

if user_item_df is None or rules_df is None:
    st.error("Missing user_item_dl.csv or rules.csv in data/ folder.")
    st.stop()

# Build antecedent item set
ante_set: set[str] = set()
for row in rules_df["antecedent"].astype(str):
    try:
        ante_set.update([i.strip().lower() for i in ast.literal_eval(row)])
    except Exception:
        ante_set.add(row.strip().lower())

# Config & CSS
API_URL = os.getenv("API_URL", "http://localhost:8000")
st.set_page_config("Hybrid Recommender System", "💼", layout="centered")
css_path = pathlib.Path(__file__).parent / "style.css"
if css_path.exists():
    st.markdown(f"<style>{css_path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)

# Helpers
def lookup_meta(name: str):
    """Tra cứu thông tin sản phẩm theo tên (item_id)."""
    if products_df is None:
        return {"name": name, "price": None, "category": None}

    match = products_df.loc[products_df.item_id.str.lower() == name.lower()]

    if not match.empty:
        info = match.iloc[0]
        return {
            "name": name,
            "price": info.price,
            "category": info.category
        }

    return {"name": name, "price": None, "category": None}


def html_card(meta, score=None):
    """Tạo HTML cho một sản phẩm."""
    parts = [f"<strong>{meta['name']}</strong>"]

    if meta.get("price"):
        parts.append(f"<br><span class='item-price'>Price: ${meta['price']:.2f}</span>")
    if meta.get("category"):
        parts.append(f"<br><span class='item-cat'>Category: {meta['category']}</span>")
    if score is not None:
        parts.append(f"<br><span class='item-rank'>Score: {score:.4f}</span>")

    return f"<div class='recommend-item'>{''.join(parts)}</div>"


def render_block(title, items):
    """Hiển thị khối gợi ý sản phẩm."""
    st.markdown(f"<div class='recommend-box'><h3>{title}</h3><div>", unsafe_allow_html=True)

    if not items:
        st.markdown("<em>No recommendations available.</em>", unsafe_allow_html=True)
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    for item in items:
        if isinstance(item, dict):
            name = item.get("item", "")
            score = item.get("score")
        else:
            name, score = item, None

        meta = lookup_meta(name)
        st.markdown(html_card(meta, score), unsafe_allow_html=True)

    st.markdown("</div></div>", unsafe_allow_html=True)

# User list
user_rank = user_item_df["user_id"].value_counts().rename_axis("user_id").reset_index(name="count")
all_user_ids = user_rank.user_id.astype(int).tolist()

# UI
st.markdown("<h2>Hybrid Recommender System</h2>", unsafe_allow_html=True)
col_u, col_i = st.columns(2)

with col_u:
    sel_user = st.selectbox("Select User", all_user_ids)
    cnt = user_rank[user_rank.user_id == sel_user]["count"].iat[0]
    st.write(f"Total items purchased: **{cnt}**")

# Item list (filter those covered by rules)
user_items = user_item_df[user_item_df.user_id == sel_user]["item_id"].unique().tolist()
rule_items = [i for i in user_items if i.lower().strip() in ante_set]

with col_i:
    chosen = st.multiselect("Select products (covered by FP-Growth rules)", options=rule_items)
    if not rule_items:
        st.info("This user has no items covered by FP-Growth rules. AI-based suggestions will still be generated.")

k = st.slider("Top-K Recommendations", 1, 10, 3)
if st.button("Generate Recommendations", disabled=len(chosen) == 0 and len(rule_items) > 0):
    st.markdown("---")
    with st.spinner("Fetching recommendations..."):
        # AI recommendations
        ai_rec = []
        try:
            r = requests.get(f"{API_URL}/recommend/by-user", params={"user_id": sel_user, "top_k": k}, timeout=30)
            ai_rec = r.json().get("results", [])
        except Exception as e:
            st.error(f"NCF Recommendation Error: {e}")

        # FP-Growth recommendations
        fp_pool = []
        for p in chosen:
            try:
                r = requests.get(f"{API_URL}/recommend/by-item", params={"item": p, "top_k": k}, timeout=30)
                fp_pool.extend(r.json().get("results", []))
            except Exception as e:
                st.error(f"FP-Growth Recommendation Error for '{p}': {e}")

        # Deduplicate by item name and filter out already selected
        chosen_lower = set(i.strip().lower() for i in chosen)
        fp_seen = set()
        fp_rec = []

        for x in fp_pool:
            name = x.get("item", "").strip().lower()
            if name and name not in chosen_lower and name not in fp_seen:
                fp_rec.append(x)
                fp_seen.add(name)
            if len(fp_rec) >= k:
                break

    col1, col2 = st.columns(2)

    with col1:
        render_block("Neural Collaborative Filtering (NCF) Recommendations", ai_rec)

    with col2:
        render_block("FP-Growth Based Suggestions", fp_rec)

    st.markdown("---")

st.caption("Developed using FP-Growth Algorithm and NCF Hybrid Recommendation Model")
