from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ma_deliberation_demo import run_deliberation  # noqa: E402

st.set_page_config(page_title="多智能体议事厅 Demo", layout="wide")
st.title("参与式规划多智能体议事厅 Demo")

topic = st.text_input("输入议题", "小区门口夜市是否应该保留？")
if st.button("启动议事", type="primary"):
    result = run_deliberation(topic, ROOT / "data" / "evidence_cards.csv")
    st.subheader("议题分析")
    st.write(result.topic_analysis)

    st.subheader("议事过程")
    for utt in result.transcript:
        with st.chat_message("assistant" if utt.speaker == "Moderator" else "user"):
            st.markdown(f"**{utt.speaker}｜{utt.phase}｜立场 {utt.stance:.2f}**")
            st.write(utt.content)
            if utt.evidence_ids:
                st.caption("证据：" + ", ".join(utt.evidence_ids))

    st.subheader("Observer 面板")
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Grounding 率", f"{result.metrics.grounding_rate:.1%}")
        st.metric("发言公平性 Gini", f"{result.metrics.fairness_gini:.3f}")
        share_df = pd.DataFrame([
            {"agent": k, "speaking_share": v} for k, v in result.metrics.speaking_share.items()
        ])
        st.bar_chart(share_df.set_index("agent"))
    with col2:
        consensus_df = pd.DataFrame(result.metrics.consensus_history)
        if not consensus_df.empty:
            st.line_chart(consensus_df.set_index("round_id")[["consensus_score", "stance_variance"]])
        stance_df = pd.DataFrame(result.metrics.stance_history)
        if not stance_df.empty:
            st.dataframe(stance_df, use_container_width=True)

    st.subheader("自动生成议事报告")
    st.markdown(result.report_markdown)
