import streamlit as st
from openai import OpenAI
import os

st.set_page_config(page_title="GPT-OSS 聊天助手", layout="centered")
st.title("🧠 GPT-OSS 聊天助手")

hf_token = st.text_input("請輸入你的 Hugging Face Token", type="password")
user_input = st.text_area("請輸入你的訊息 👇", height=100)

if st.button("送出對話") and hf_token and user_input:
    try:
        os.environ["HF_TOKEN"] = hf_token
        client = OpenAI(base_url="https://router.huggingface.co/v1",
                        api_key=hf_token)
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b:cerebras",
            messages=[{
                "role": "user",
                "content": user_input
            }])
        st.success("🗣️ 模型回覆：")
        st.write(response.choices[0].message.content)
    except Exception as e:
        st.error(f"⚠️ 發生錯誤：{e}")
elif not hf_token:
    st.warning("請輸入 Hugging Face Token 才能使用！")
