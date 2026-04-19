import os
import google.generativeai as genai
from github import Github

# 設定値
ORG_NAME = "cac-it-training-2026"
ASSIGNMENT_PREFIX = "java-" # Classroomで設定した課題名のプレフィックス
TARGET_FILE = "java_comprehension_exercises_volume1/src/**/*.java"    # 分析したいファイルパス

# 認証設定
github_token = os.getenv("ORG_READ_TOKE")
gemini_key = os.getenv("GEMINI_API_KEY")

g = Github(github_token)
genai.configure(api_key=gemini_key)

# 注意: 大量のコードを読み込ませるため、必ず 'gemini-1.5-pro' を使用します
model = genai.GenerativeModel('gemini-1.5-pro')

def collect_student_code():
    org = g.get_organization(ORG_NAME)
    all_code_data = ""
    
    # 課題プレフィックスに一致する全リポジトリを取得
    for repo in org.get_repos():
        if repo.name.startswith(ASSIGNMENT_PREFIX):
            student_id = repo.name.replace(ASSIGNMENT_PREFIX, "")
            try:
                # 対象ファイルのコードを取得
                file_content = repo.get_contents(TARGET_FILE)
                code = file_content.decoded_content.decode('utf-8')
                
                # 誰のコードかわかるように区切り文字を入れる
                all_code_data += f"\n\n====================\n"
                all_code_data += f"Student: {student_id}\n"
                all_code_data += f"====================\n"
                all_code_data += code
            except Exception as e:
                # まだファイルが作られていない受講生はスキップ
                pass
                
    return all_code_data

def analyze_trends(code_data):
    prompt = f"""
    あなたはプロのJava技術研修講師です。
    以下に、新入社員120名が提出したJavaの練習問題のコードを列挙します。
    これらを全体的に分析し、以下のフォーマットでレポートを作成してください。
    
    【出力フォーマット】
    1. クラス全体の理解度サマリー（よくできている点）
    2. 全体に共通して見られる「アンチパターン」や「誤解」のトップ3
    3. 明日の講義で補足説明すべき重要な概念
    4. （もしあれば）特異な実装をしており、個別フォローが必要かもしれない受講生IDと理由
    
    【受講生コード一覧】
    {code_data}
    """
    
    response = model.generate_content(prompt)
    return response.text

if __name__ == "__main__":
    print("受講生コードを収集しています...")
    combined_code = collect_student_code()
    
    print("Geminiによるバッチ解析を実行中...")
    report = analyze_trends(combined_code)
    
    print("\n【解析レポート】\n")
    print(report)
    
    # ※ここでSlack APIなどを叩いて送信する処理を入れるとさらに便利です
