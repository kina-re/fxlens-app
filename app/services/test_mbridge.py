# app/services/test_mbridge.py

from mbridge import ask_qwen, qwen_healthcheck


def main():
    print("🔍 Checking Qwen health...")
    if qwen_healthcheck():
        print("✅ Qwen API is running!")

        # Try a simple question
        question = "Give me a SQL query to count the number of rows in a table."
        print(f"\n📝 Asking Qwen: {question}")
        sql = ask_qwen(question)
        print(f"\n📌 Qwen Response:\n{sql}\n")

    else:
        print("❌ Qwen API is NOT running. Start Qwen first.")


if __name__ == "__main__":
    main()
