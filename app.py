import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time
import os

# Set page config with dark theme/visual style
st.set_page_config(
    page_title="Swing Trade Engine - Kotak Neo",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for modern premium dashboard (dark mode, glassmorphism, nice badges)
st.markdown("""
<style>
    /* Custom background and fonts */
    .stApp {
        background-color: #0b0f19;
        color: #e2e8f0;
    }
    
    /* Header Style */
    .header-container {
        padding: 1.5rem;
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        border-radius: 12px;
        border: 1px solid #334155;
        margin-bottom: 2rem;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
    }
    .header-title {
        font-size: 2.2rem;
        font-weight: 800;
        background: linear-gradient(to right, #60a5fa, #3b82f6);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin: 0;
    }
    .header-subtitle {
        color: #94a3b8;
        font-size: 1rem;
        margin-top: 0.3rem;
    }
    
    /* Card design */
    .metric-card {
        background: #1e293b;
        border: 1px solid #334155;
        border-radius: 10px;
        padding: 1.2rem;
        text-align: center;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
    }
    
    /* Custom buttons */
    .stButton>button {
        background: linear-gradient(to right, #2563eb, #1d4ed8);
        color: white;
        border-radius: 6px;
        border: none;
        padding: 0.5rem 1.5rem;
        font-weight: 600;
        transition: all 0.2s ease-in-out;
    }
    .stButton>button:hover {
        background: linear-gradient(to right, #3b82f6, #2563eb);
        box-shadow: 0 0 12px rgba(59, 130, 246, 0.5);
    }
    
    /* Table styling */
    .opportunity-table {
        width: 100%;
        border-collapse: collapse;
        margin: 1rem 0;
        font-size: 0.95rem;
        border-radius: 8px;
        overflow: hidden;
    }
    .opportunity-table th {
        background-color: #1e293b;
        color: #94a3b8;
        text-align: left;
        padding: 10px 15px;
        font-weight: 600;
        border-bottom: 2px solid #334155;
    }
    .opportunity-table td {
        padding: 12px 15px;
        border-bottom: 1px solid #1e293b;
        background-color: #0f172a;
    }
    .opportunity-table tr:hover td {
        background-color: #1e293b;
    }
    
    /* Badges */
    .badge {
        padding: 3px 8px;
        border-radius: 12px;
        font-size: 0.8rem;
        font-weight: 600;
        display: inline-block;
    }
    .badge-rsi { background-color: #1e3a8a; color: #93c5fd; }
    .badge-ema { background-color: #312e81; color: #c7d2fe; }
    .badge-macd { background-color: #14532d; color: #86efac; }
    .badge-bb { background-color: #581c87; color: #f3e8ff; }
    
    .badge-connected { background-color: #065f46; color: #34d399; }
    .badge-disconnected { background-color: #7f1d1d; color: #f87171; }
</style>
""", unsafe_allow_html=True)

# Import backend modules inside functions or after page config to avoid issues
import config
from kotak_auth import KotakNeoSession
import scanner

# Initialize session state variables
if "kotak_session" not in st.session_state:
    st.session_state.kotak_session = KotakNeoSession()

if "opportunities" not in st.session_state:
    st.session_state.opportunities = []

if "scan_completed" not in st.session_state:
    st.session_state.scan_completed = False

if "selected_setup" not in st.session_state:
    st.session_state.selected_setup = None

# Sidebar Authentication Panel
st.sidebar.markdown("### 🔑 Kotak Neo API Credentials")

# Pre-populate sidebar fields with environment values
sidebar_key = st.sidebar.text_input("Consumer Key", value=config.KOTAK_CONSUMER_KEY, type="password")
sidebar_mobile = st.sidebar.text_input("Mobile Number", value=config.KOTAK_MOBILE)
sidebar_ucc = st.sidebar.text_input("UCC (Client Code)", value=config.KOTAK_UCC)
sidebar_mpin = st.sidebar.text_input("6-digit MPIN", value=config.KOTAK_MPIN, type="password")

use_auto_totp = st.sidebar.checkbox("Auto-generate TOTP (needs secret)", value=bool(config.KOTAK_TOTP_SECRET))
sidebar_totp_secret = ""
if use_auto_totp:
    sidebar_totp_secret = st.sidebar.text_input("TOTP Secret Key", value=config.KOTAK_TOTP_SECRET, type="password")
else:
    manual_totp_val = st.sidebar.text_input("Enter 6-digit TOTP", type="default")

# Update credentials in our session object if inputs changed
st.session_state.kotak_session.consumer_key = sidebar_key
st.session_state.kotak_session.mobile = sidebar_mobile
st.session_state.kotak_session.ucc = sidebar_ucc
st.session_state.kotak_session.mpin = sidebar_mpin
if use_auto_totp:
    st.session_state.kotak_session.totp_secret = sidebar_totp_secret
else:
    st.session_state.kotak_session.totp_secret = ""

# Authentication trigger buttons
col_auth1, col_auth2 = st.sidebar.columns(2)
with col_auth1:
    if st.button("🔌 Connect"):
        with st.spinner("Authenticating Kotak Neo..."):
            totp_code = None if use_auto_totp else manual_totp_val
            success, msg = st.session_state.kotak_session.login(manual_totp=totp_code)
            if success:
                st.sidebar.success("Logged in successfully!")
            else:
                st.sidebar.error(f"Login failed: {msg}")

with col_auth2:
    if st.button("❌ Disconnect"):
        st.session_state.kotak_session = KotakNeoSession()
        st.sidebar.info("Disconnected session.")

# Status display in sidebar
is_auth = st.session_state.kotak_session.is_authenticated
status_html = '<span class="badge badge-connected">Connected</span>' if is_auth else '<span class="badge badge-disconnected">Disconnected</span>'
st.sidebar.markdown(f"**Session Status:** {status_html}", unsafe_allow_html=True)


# Main Header Component
st.markdown(f"""
<div class="header-container">
    <div style="display: flex; justify-content: space-between; align-items: center;">
        <div>
            <h1 class="header-title">⚡ Swing Trade Engine</h1>
            <div class="header-subtitle">Scan for high-probability setups & trade via Kotak Neo API</div>
        </div>
        <div style="text-align: right;">
            <div style="font-size: 0.85rem; color: #94a3b8;">KOTAK NEO SESSION</div>
            <div style="margin-top: 0.2rem;">{status_html}</div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)


# Layout Tabs
tab1, tab2, tab3 = st.tabs(["🔍 Swing Scanner", "📊 Visualizer", "💼 Portfolio & Trading"])

# --- TAB 1: SWING SCANNER ---
with tab1:
    st.markdown("### 📡 Scan Opportunities")
    
    col_sc1, col_sc2, col_sc3 = st.columns([2, 2, 1])
    with col_sc1:
        watchlist = st.selectbox("Select Watchlist", config.AVAILABLE_WATCHLISTS)
    with col_sc2:
        strategies_selected = st.multiselect(
            "Strategies to Run", 
            ["RSI Reversal", "EMA Pullback", "MACD Crossover", "BB Rebound"],
            default=["RSI Reversal", "EMA Pullback", "MACD Crossover", "BB Rebound"]
        )
    with col_sc3:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        scan_btn = st.button("🚀 Start Scan")

    if scan_btn:
        if not strategies_selected:
            st.warning("Please select at least one strategy.")
        else:
            with st.spinner("Downloading historical data and scanning watchlists... This may take up to a minute."):
                opportunities = scanner.run_scanner(
                    watchlist_name=watchlist,
                    kotak_session=st.session_state.kotak_session
                )
                # Filter by selected strategies
                filtered_opps = [o for o in opportunities if o["Strategy"] in strategies_selected]
                st.session_state.opportunities = filtered_opps
                st.session_state.scan_completed = True
                
                if filtered_opps:
                    st.success(f"Scan complete! Identified {len(filtered_opps)} potential swing trading opportunities.")
                else:
                    st.info("No matching swing setups found on the selected watchlist and strategy settings.")

    # Show Scan Results Table
    if st.session_state.scan_completed:
        opps = st.session_state.opportunities
        if opps:
            # Convert to DataFrame for easier display
            df_opps = pd.DataFrame(opps)
            
            # Show summary stats
            col_stat1, col_stat2, col_stat3 = st.columns(3)
            with col_stat1:
                st.markdown(f"""
                <div class="metric-card">
                    <div style="font-size: 0.9rem; color: #94a3b8;">Total Opportunities</div>
                    <div style="font-size: 1.8rem; font-weight: 700; color: #60a5fa; margin-top: 0.3rem;">{len(df_opps)}</div>
                </div>
                """, unsafe_allow_html=True)
            with col_stat2:
                best_rr = df_opps['RiskReward'].max()
                st.markdown(f"""
                <div class="metric-card">
                    <div style="font-size: 0.9rem; color: #94a3b8;">Highest Risk-to-Reward</div>
                    <div style="font-size: 1.8rem; font-weight: 700; color: #34d399; margin-top: 0.3rem;">{best_rr}:1</div>
                </div>
                """, unsafe_allow_html=True)
            with col_stat3:
                most_common = df_opps['Strategy'].mode()[0] if not df_opps.empty else "N/A"
                st.markdown(f"""
                <div class="metric-card">
                    <div style="font-size: 0.9rem; color: #94a3b8;">Most Active Strategy</div>
                    <div style="font-size: 1.8rem; font-weight: 700; color: #c7d2fe; margin-top: 0.3rem;">{most_common}</div>
                </div>
                """, unsafe_allow_html=True)
                
            st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)
            
            # Interactive Selection
            st.markdown("### 📋 Identified Setups")
            st.markdown("Select a row below to load it into the **Visualizer** or configure a trade order.")
            
            # Display dataframe (compatible with older Streamlit versions)
            st.dataframe(
                df_opps[["Symbol", "Strategy", "Entry", "StopLoss", "Target", "RiskReward", "Details"]],
                use_container_width=True
            )
            
            # Selectbox for setup loading
            st.markdown("#### 🔍 Select Setup to Visualize / Trade")
            setup_options = [f"{o['Symbol']} ({o['Strategy']}) - RR: {o['RiskReward']}" for o in opps]
            
            # Keep index if already selected, otherwise default to 0
            default_index = 0
            if st.session_state.selected_setup in opps:
                default_index = opps.index(st.session_state.selected_setup)
                
            selected_option = st.selectbox(
                "Choose an opportunity to view in the Visualizer / Trading tabs:", 
                setup_options,
                index=default_index
            )
            
            if selected_option:
                selected_idx = setup_options.index(selected_option)
                st.session_state.selected_setup = opps[selected_idx]
                st.success(f"Loaded {st.session_state.selected_setup['Symbol']} ({st.session_state.selected_setup['Strategy']}) setup. Switch to the **Visualizer** or **Portfolio & Trading** tabs.")
        else:
            st.info("No opportunities identified yet. Start a scan using the controls above.")
    else:
        st.info("Scanner is idle. Select watchlist and click 'Start Scan' above.")

# --- TAB 2: VISUALIZER ---
with tab2:
    st.markdown("### 📊 Interactive Chart Visualizer")
    
    setup = st.session_state.selected_setup
    if not setup:
        st.info("Please run the scanner and select an opportunity from the setups list to visualize the chart.")
    else:
        symbol = setup["Symbol"]
        strategy = setup["Strategy"]
        entry = setup["Entry"]
        sl = setup["StopLoss"]
        target = setup["Target"]
        
        st.markdown(f"#### Chart for **{symbol}** ({strategy} Strategy)")
        
        with st.spinner("Downloading chart data..."):
            df_chart = scanner.fetch_historical_data(symbol, period="1y")
            
        if df_chart is not None and not df_chart.empty:
            # Recompute indicator columns for plotting
            import strategies as strat
            df_chart['EMA20'] = strat.calculate_ema(df_chart, 20)
            df_chart['EMA50'] = strat.calculate_ema(df_chart, 50)
            
            # Create Plotly Candlestick Subplots
            # (If MACD strategy, add a MACD panel, else just single chart)
            if strategy == "MACD Crossover":
                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                                    vertical_spacing=0.08, row_heights=[0.7, 0.3])
                
                macd_line, sig_line, macd_hist = strat.calculate_macd(df_chart)
                
                fig.add_trace(go.Scatter(x=df_chart['Date'], y=macd_line, name="MACD", line=dict(color='#3b82f6')), row=2, col=1)
                fig.add_trace(go.Scatter(x=df_chart['Date'], y=sig_line, name="Signal", line=dict(color='#f97316')), row=2, col=1)
                # Color code histogram bars
                colors = ['#22c55e' if val >= 0 else '#ef4444' for val in macd_hist]
                fig.add_trace(go.Bar(x=df_chart['Date'], y=macd_hist, name="Hist", marker_color=colors), row=2, col=1)
            elif strategy == "BB Rebound":
                fig = make_subplots(rows=1, cols=1)
                upper, middle, lower = strat.calculate_bollinger_bands(df_chart)
                fig.add_trace(go.Scatter(x=df_chart['Date'], y=upper, name="Upper BB", line=dict(color='#8b5cf6', dash='dash')))
                fig.add_trace(go.Scatter(x=df_chart['Date'], y=middle, name="Middle BB", line=dict(color='#64748b')))
                fig.add_trace(go.Scatter(x=df_chart['Date'], y=lower, name="Lower BB", line=dict(color='#8b5cf6', dash='dash')))
            else:
                fig = make_subplots(rows=1, cols=1)
                fig.add_trace(go.Scatter(x=df_chart['Date'], y=df_chart['EMA20'], name="20 EMA", line=dict(color='#3b82f6', width=1.5)))
                fig.add_trace(go.Scatter(x=df_chart['Date'], y=df_chart['EMA50'], name="50 EMA", line=dict(color='#f59e0b', width=1.5)))
            
            # Add Candlesticks to Row 1
            fig.add_trace(go.Candlestick(
                x=df_chart['Date'],
                open=df_chart['Open'],
                high=df_chart['High'],
                low=df_chart['Low'],
                close=df_chart['Close'],
                name="OHLC"
            ), row=1, col=1)
            
            # Draw horizontal levels for Buy Entry, Target, Stop Loss
            fig.add_hline(y=entry, line_dash="dot", annotation_text=f"Buy Entry: {entry}", 
                          annotation_position="top right", line_color="#3b82f6", line_width=1.5, row=1, col=1)
            fig.add_hline(y=sl, line_dash="dot", annotation_text=f"Stop Loss: {sl}", 
                          annotation_position="bottom right", line_color="#ef4444", line_width=1.5, row=1, col=1)
            fig.add_hline(y=target, line_dash="dot", annotation_text=f"Target: {target}", 
                          annotation_position="top right", line_color="#22c55e", line_width=1.5, row=1, col=1)
            
            # Layout customization
            fig.update_layout(
                height=650,
                xaxis_rangeslider_visible=False,
                template="plotly_dark",
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                margin=dict(l=20, r=20, t=20, b=20),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.error("Failed to load historical data for chart generation.")

# --- TAB 3: PORTFOLIO & TRADING ---
with tab3:
    st.markdown("### 💼 Kotak Neo Account & Orders")
    
    if not is_auth:
        st.warning("Please connect to your Kotak Neo API in the sidebar to view portfolio and place orders.")
    else:
        # Columns for Holdings and Open Positions
        col_port1, col_port2 = st.columns(2)
        
        with col_port1:
            st.markdown("#### 📁 Current Holdings")
            with st.spinner("Fetching holdings..."):
                holdings, err = st.session_state.kotak_session.get_holdings()
                if err:
                    st.error(f"Error fetching holdings: {err}")
                elif holdings:
                    # Kotak Neo API returns holdings in custom format.
                    # Convert to dataframe and show.
                    st.json(holdings)
                else:
                    st.info("No holdings found or empty response.")
                    
        with col_port2:
            st.markdown("#### 🔄 Open Positions")
            with st.spinner("Fetching positions..."):
                positions, err = st.session_state.kotak_session.get_positions()
                if err:
                    st.error(f"Error fetching positions: {err}")
                elif positions:
                    st.json(positions)
                else:
                    st.info("No open positions found.")
                    
        # Order Execution Panel
        st.markdown("<hr>", unsafe_allow_html=True)
        st.markdown("### 🛒 Place Swing Trade Order")
        
        setup = st.session_state.selected_setup
        
        col_ord1, col_ord2 = st.columns(2)
        with col_ord1:
            ord_symbol = st.text_input("Trading Symbol", value=setup["Symbol"] if setup else "")
            ord_clean = config.get_clean_symbol(ord_symbol)
            
            # Quantity Calculation helper
            risk_budget = st.number_input("Max Risk Amount (INR)", value=1000.0, step=100.0)
            
            if setup and ord_symbol == setup["Symbol"]:
                calc_qty = int(risk_budget / max(1, (setup["Entry"] - setup["StopLoss"])))
            else:
                calc_qty = 1
                
            qty = st.number_input("Order Quantity", value=calc_qty, min_value=1, step=1)
            
        with col_ord2:
            limit_price = st.number_input("Limit Price (INR)", value=setup["Entry"] if setup else 0.0, step=0.05)
            ord_type = st.selectbox("Order Type", ["LIMIT", "MARKET"])
            product_type = st.selectbox("Product Type", ["CNC", "MIS"]) # CNC = Cash & Carry (Swing/Delivery)
            
        # Execute button
        if st.button("⚡ Submit Order"):
            with st.spinner("Submitting order to Kotak Neo..."):
                res, err = st.session_state.kotak_session.place_swing_order(
                    symbol=ord_symbol,
                    quantity=qty,
                    transaction_type="BUY",
                    order_type=ord_type,
                    price=limit_price if ord_type == "LIMIT" else None,
                    product=product_type
                )
                if err:
                    st.error(f"Order failed: {err}")
                else:
                    st.success(f"Order placed successfully! Response: {res}")
