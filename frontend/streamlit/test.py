import streamlit as st

st.set_page_config(page_title="TrustFlow Guardian", layout="wide", initial_sidebar_state="expanded")

# ─── Custom CSS ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .block-container { padding-top: 1rem; padding-bottom: 0rem; }
    [data-testid="stSidebar"] { background-color: #1e293b; border-right: 1px solid #334155; }
    .guardian-logo { font-size: 22px; font-weight: 700; color: #e2e8f0; }
    .guardian-status { color: #10b981; font-size: 13px; margin-top: 4px; }
    .chat-header { display:flex; align-items:center; justify-content:space-between; padding:12px 0; border-bottom:1px solid #374151; margin-bottom:16px; }
    .chat-header-title { font-size:16px; font-weight:600; color:#f1f5f9; }
    .chat-header-sub { font-size:12px; color:#94a3b8; }
    .auth-badge { background-color:#451a1a; color:#fca5a5; padding:4px 10px; border-radius:12px; font-size:12px; font-weight:500; }
    .user-message { background:linear-gradient(135deg,#3b82f6,#2563eb); color:white; padding:12px 16px; border-radius:16px 16px 4px 16px; max-width:80%; font-size:14px; margin-left:auto; }
    .msg-time { font-size:11px; color:#64748b; text-align:right; margin-bottom:16px; }
    .bot-header { display:flex; align-items:center; gap:8px; margin-bottom:12px; }
    .bot-avatar { width:28px; height:28px; background:linear-gradient(135deg,#3b82f6,#1d4ed8); border-radius:50%; display:flex; align-items:center; justify-content:center; color:white; font-size:14px; }
    .bot-name { font-weight:600; font-size:14px; color:#f1f5f9; }
    .bot-time { font-size:12px; color:#64748b; }
    .risk-card { border:1px solid #374151; border-radius:12px; padding:20px; background:#1f2937; box-shadow:0 1px 3px rgba(0,0,0,0.3); }
    .risk-card-header { display:flex; align-items:center; justify-content:space-between; margin-bottom:16px; }
    .risk-card-title { font-size:16px; font-weight:700; color:#f1f5f9; }
    .risk-badge-high { background-color:#dc2626; color:white; padding:4px 12px; border-radius:6px; font-size:12px; font-weight:700; }
    .risk-score-label { font-size:12px; font-weight:600; color:#94a3b8; text-transform:uppercase; margin-bottom:8px; }
    .risk-score-row { display:flex; align-items:center; justify-content:space-between; margin-bottom:6px; }
    .risk-score-text { font-size:13px; color:#cbd5e1; }
    .risk-score-value { font-size:18px; font-weight:700; color:#f87171; }
    .risk-bar { height:8px; border-radius:4px; background:linear-gradient(to right,#10b981,#f59e0b,#dc2626); position:relative; margin-bottom:4px; }
    .risk-bar-indicator { position:absolute; right:9%; top:-4px; width:16px; height:16px; background:#1f2937; border:3px solid #dc2626; border-radius:50%; }
    .risk-bar-labels { display:flex; justify-content:space-between; font-size:11px; color:#64748b; }
    .warning-item { display:flex; gap:12px; padding:10px 0; border-top:1px solid #374151; }
    .warning-icon-red { width:24px; height:24px; background-color:#451a1a; border-radius:50%; display:flex; align-items:center; justify-content:center; flex-shrink:0; color:#f87171; font-size:12px; }
    .warning-icon-yellow { width:24px; height:24px; background-color:#451f0a; border-radius:50%; display:flex; align-items:center; justify-content:center; flex-shrink:0; color:#fbbf24; font-size:12px; }
    .warning-title { font-size:13px; font-weight:600; color:#f1f5f9; margin-bottom:2px; }
    .warning-desc { font-size:12px; color:#94a3b8; }
    .info-box { background-color:#172554; border:1px solid #1e40af; border-radius:8px; padding:12px 16px; margin-top:12px; display:flex; align-items:center; gap:10px; }
    .info-box-text { font-size:13px; color:#93c5fd; }
    .action-buttons { display:flex; gap:12px; margin-top:16px; }
    .btn-danger { background:linear-gradient(135deg,#ef4444,#dc2626); color:white; padding:10px 20px; border-radius:8px; font-size:13px; font-weight:600; border:none; flex:1; text-align:center; }
    .btn-outline { background:#1f2937; color:#cbd5e1; padding:10px 20px; border-radius:8px; font-size:13px; font-weight:500; border:1px solid #4b5563; text-align:center; }
    .ai-panel-title { font-size:15px; font-weight:700; color:#f1f5f9; margin-bottom:2px; }
    .ai-panel-subtitle { font-size:12px; color:#64748b; margin-bottom:16px; }
    .step-item { display:flex; gap:12px; margin-bottom:16px; }
    .step-circle-blue { width:32px; height:32px; background-color:#3b82f6; border-radius:50%; display:flex; align-items:center; justify-content:center; color:white; font-size:14px; flex-shrink:0; }
    .step-circle-red { width:32px; height:32px; background-color:#dc2626; border-radius:50%; display:flex; align-items:center; justify-content:center; color:white; font-size:14px; flex-shrink:0; }
    .step-content { flex:1; }
    .step-header { display:flex; justify-content:space-between; align-items:center; }
    .step-title { font-size:13px; font-weight:700; color:#f1f5f9; }
    .step-number { font-size:11px; color:#64748b; }
    .step-desc { font-size:12px; color:#94a3b8; margin-top:2px; }
    .step-detail { font-size:12px; color:#60a5fa; margin-top:4px; font-style:italic; }
    .step-detail-red { font-size:12px; color:#f87171; margin-top:4px; font-weight:500; }
    .sub-agent-box { display:flex; gap:8px; margin-top:8px; }
    .sub-agent-item { background:#1e293b; border:1px solid #374151; border-radius:8px; padding:8px 12px; flex:1; text-align:center; }
    .sub-agent-name { font-size:12px; font-weight:600; color:#f1f5f9; }
    .sub-agent-desc { font-size:10px; color:#94a3b8; margin-top:2px; }
    .sub-agent-status-ok { font-size:10px; color:#10b981; margin-top:4px; }
    .sub-agent-status-fail { font-size:10px; color:#94a3b8; margin-top:4px; }
    .history-item { padding:10px 12px; border-radius:8px; margin-bottom:4px; }
    .history-item-active { background-color:#1e3a5f; border-left:3px solid #3b82f6; }
    .history-item-title { font-size:13px; font-weight:500; color:#cbd5e1; }
    .history-item-title-active { font-size:13px; font-weight:600; color:#60a5fa; }
    .history-item-time { font-size:11px; color:#64748b; }
    .footer-text { text-align:center; font-size:11px; color:#64748b; margin-top:12px; }
</style>
""", unsafe_allow_html=True)

# ─── Sidebar ───────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
        <div style="padding:8px 0 16px 0;">
            <div class="guardian-logo">🛡️ TrustFlow<br><span style="font-size:14px; font-weight:400; color:#64748b;">Guardian</span></div>
            <div class="guardian-status">● Guardian Đang Hoạt Động</div>
        </div>
    """, unsafe_allow_html=True)

    st.button("➕ Đoạn Chat Mới", use_container_width=True, type="primary")

    st.markdown("<p style='font-size:11px; color:#9ca3af; font-weight:600; margin-top:16px;'>LỊCH SỬ</p>", unsafe_allow_html=True)

    st.markdown("""
        <div class="history-item history-item-active">
            <div class="history-item-title-active">💬 Chuyển tiền cho Minh</div>
            <div class="history-item-time">10:21 SA</div>
        </div>
        <div class="history-item">
            <div class="history-item-title">☐ Kiểm tra chi tiêu tháng này</div>
            <div class="history-item-time">Hôm qua</div>
        </div>
        <div class="history-item">
            <div class="history-item-title">☐ Tư vấn mở thẻ tín dụng</div>
            <div class="history-item-time">Thứ Hai</div>
        </div>
        <div class="history-item">
            <div class="history-item-title">☐ Báo cáo số dư tài khoản</div>
            <div class="history-item-time">Tuần trước</div>
        </div>
    """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("""
        <div style="display:flex; align-items:center; gap:8px;">
            <div style="width:32px; height:32px; background:#e5e7eb; border-radius:50%; display:flex; align-items:center; justify-content:center;">👤</div>
            <div>
                <div style="font-size:13px; font-weight:600; color:#1f2937;">Nguyễn Phương ...</div>
                <div style="font-size:11px; color:#9ca3af;">Tài khoản Premium</div>
            </div>
            <div style="margin-left:auto;">⚙️</div>
        </div>
    """, unsafe_allow_html=True)

# ─── Main Layout ──────────────────────────────────────────────────────────
main_col, right_col = st.columns([3, 1.2])

with main_col:
    # Chat header
    st.markdown("""
        <div class="chat-header">
            <div>
                <div class="chat-header-title">⚠️ Giao Dịch Chuyển Tiền An Toàn</div>
                <div class="chat-header-sub">Phiên hoạt động • 10:21 SA</div>
            </div>
            <div class="auth-badge">● Cần xác thực</div>
        </div>
    """, unsafe_allow_html=True)

    # User message
    st.markdown("""
        <div style="display:flex; justify-content:flex-end; margin-bottom:4px;">
            <div class="user-message">Chuyển cho Minh 2 triệu như tháng trước</div>
        </div>
        <div class="msg-time">10:21 SA</div>
    """, unsafe_allow_html=True)

    # Bot response
    st.markdown("""
        <div class="bot-header">
            <div class="bot-avatar">🛡</div>
            <span class="bot-name">TrustFlow Guardian</span>
            <span class="bot-time">10:21 SA</span>
        </div>
    """, unsafe_allow_html=True)

    # Risk card
    st.markdown("""
        <div class="risk-card">
            <div class="risk-card-header">
                <div class="risk-card-title">⚡ Phân Tích Rủi Ro Giao Dịch</div>
                <div class="risk-badge-high">RỦI RO CAO</div>
            </div>
            <div style="margin-bottom:16px;">
                <div class="risk-score-label">ĐIỂM RỦI RO</div>
                <div class="risk-score-row">
                    <div class="risk-score-text">Thang đo rủi ro</div>
                    <div class="risk-score-value">0.91 <span style="font-size:12px;">đỏ</span></div>
                </div>
                <div class="risk-bar"><div class="risk-bar-indicator"></div></div>
                <div class="risk-bar-labels">
                    <span>🟢 An toàn</span>
                    <span>🟡 Trung bình</span>
                    <span>🔴 Nguy hiểm</span>
                </div>
            </div>
            <div class="warning-item">
                <div class="warning-icon-red">✕</div>
                <div>
                    <div class="warning-title">Bất thường: Số tiền cao hơn mức trung bình</div>
                    <div class="warning-desc">2.000.000 VNĐ — vượt 340% mức giao dịch thông thường</div>
                </div>
            </div>
            <div class="warning-item">
                <div class="warning-icon-red">✕</div>
                <div>
                    <div class="warning-title">Người nhận mới: Giao dịch lần đầu tiên</div>
                    <div class="warning-desc">Không tìm thấy lịch sử giao dịch với "Minh"</div>
                </div>
            </div>
            <div class="warning-item">
                <div class="warning-icon-yellow">⚠</div>
                <div>
                    <div class="warning-title">Phát hiện từ ngữ hối thúc trong tin nhắn</div>
                    <div class="warning-desc">Từ "như tháng trước" — tạo cảm giác giao dịch quen thuộc</div>
                </div>
            </div>
            <div class="info-box">
                <span style="font-size:18px;">🔒</span>
                <div class="info-box-text">Chúng tôi không thể hoàn thành giao dịch này do nghi ngờ có dấu hiệu lừa đảo.</div>
            </div>
            <div class="action-buttons">
                <div class="btn-danger">ⓘ Tìm hiểu thêm & Phương án an toàn</div>
                <div class="btn-outline">Hủy giao dịch</div>
            </div>
        </div>
    """, unsafe_allow_html=True)

    st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)
    st.chat_input("Nhập yêu cầu ngân hàng của bạn...")
    st.markdown('<div class="footer-text">TrustFlow Guardian bảo vệ mọi giao dịch của bạn theo thời gian thực</div>', unsafe_allow_html=True)

with right_col:
    st.markdown("""<div style="border-left:1px solid #4b5563; padding-left:16px;">
<div style="display:flex; align-items:center; gap:8px; margin-bottom:4px;">
<span style="font-size:16px;">⚡</span>
<div class="ai-panel-title">Tiến Trình Xử Lý AI</div>
</div>
<div class="ai-panel-subtitle">Luồng vận hành hệ thống</div>
</div>""", unsafe_allow_html=True)

    # Step 1
    st.markdown("""<div class="step-item">
<div class="step-circle-blue">📝</div>
<div class="step-content">
<div class="step-header"><div class="step-title">Đầu Vào Ngôn Ngữ</div><div class="step-number">#1</div></div>
<div class="step-desc">Phân tích câu lệnh tự nhiên</div>
<div class="step-detail">"Chuyển cho Minh 2 triệu như tháng trước."</div>
</div></div>""", unsafe_allow_html=True)

    # Step 2
    st.markdown("""<div class="step-item">
<div class="step-circle-blue">🔀</div>
<div class="step-content">
<div class="step-header"><div class="step-title">Orchestrator Điều Phối</div><div class="step-number">#2</div></div>
<div class="step-desc">Phân loại & định tuyến yêu cầu</div>
<div class="step-detail">→ Transaction Agent</div>
</div></div>""", unsafe_allow_html=True)

    # Step 3
    st.markdown("""<div class="step-item">
<div class="step-circle-blue">🤝</div>
<div class="step-content">
<div class="step-header"><div class="step-title">Hợp Tác Sub-Agent</div><div class="step-number">#3</div></div>
<div class="step-desc">Tìm kiếm thông tin người nhận</div>
<div class="sub-agent-box">
<div class="sub-agent-item"><div class="sub-agent-name">📊 Text2SQL</div><div class="sub-agent-desc">Truy vấn CSDL</div><div class="sub-agent-status-ok">● Đã hoàn thành</div></div>
<div class="sub-agent-item"><div class="sub-agent-name">📜 History</div><div class="sub-agent-desc">Lịch sử GD</div><div class="sub-agent-status-fail">● Không tìm thấy</div></div>
</div></div></div>""", unsafe_allow_html=True)

    # Step 4
    st.markdown("""<div class="step-item">
<div class="step-circle-red">🛡</div>
<div class="step-content">
<div class="step-header"><div class="step-title">Kiểm Duyệt Guardian</div><div class="step-number">#4</div></div>
<div class="step-desc">Hệ thống kiểm soát rủi ro</div>
<div class="step-detail-red">Phát hiện rủi ro 0.91 → Chặn giao dịch</div>
</div></div>""", unsafe_allow_html=True)

    # Step 5
    st.markdown("""<div class="step-item">
<div class="step-circle-blue">📋</div>
<div class="step-content">
<div class="step-header"><div class="step-title">Nhật Ký Kiểm Toán</div><div class="step-number">#5</div></div>
<div class="step-desc">Ghi nhận & chờ xác thực</div>
<div class="step-detail">Đang chờ OTP / Tạm khóa giao dịch</div>
</div></div>""", unsafe_allow_html=True)
