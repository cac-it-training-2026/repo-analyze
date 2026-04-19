import os
from google import genai
# PyGithubの新しい認証モジュールを追加
from github import Github, Auth


# 設定値（ここを変更しました）
ORG_NAME = "cac-it-training-2026"
ASSIGNMENT_PREFIX = "java-"  # 「java-ユーザー名」に対応
BASE_DIR = "java_comprehension_exercises_volume1/src/" # 検索の起点となるディレクトリ

# 認証設定
github_token = os.getenv("ORG_READ_TOKEN")
gemini_key = os.getenv("GEMINI_API_KEY")

# --- 追加するデバッグコード ---
if not gemini_key:
    print("❌ エラー: GEMINI_API_KEYが読み込めていません！GitHubのSecret設定を確認してください。")
    exit(1)
else:
    print("✅ APIキーの読み込みに成功しました！")
# ------------------------------

# PyGithubの新しい認証方式
auth = Auth.Token(github_token)
g = Github(auth=auth)

# Geminiの新しい初期化方式
client = genai.Client(api_key=gemini_key)


def collect_student_code():
    org = g.get_organization(ORG_NAME)
    all_code_data = ""
    
    # 課題プレフィックスに一致する全リポジトリを取得
    for repo in org.get_repos():
        if repo.name.startswith(ASSIGNMENT_PREFIX):
            student_id = repo.name.replace(ASSIGNMENT_PREFIX, "")
            
            all_code_data += f"\n\n====================\n"
            all_code_data += f"Student: {student_id}\n"
            all_code_data += f"====================\n"
            
            try:
                # デフォルトブランチ（mainなど）のツリー（ファイル構造）を再帰的に全取得
                branch = repo.default_branch
                tree = repo.get_git_tree(branch, recursive=True).tree
                
                found_files = False
                for item in tree:
                    # 指定したフォルダ配下であり、かつ拡張子が .java のものを抽出
                    if item.path.startswith(BASE_DIR) and item.path.endswith(".java"):
                        # ファイルの中身を取得
                        file_content = repo.get_contents(item.path)
                        code = file_content.decoded_content.decode('utf-8')
                        
                        # ファイル名を見出しにしてコードを結合
                        all_code_data += f"\n--- File: {item.path} ---\n"
                        all_code_data += code
                        found_files = True
                        
                if not found_files:
                    all_code_data += "(対象のJavaファイルがまだ作成されていません)\n"
                    
            except Exception as e:
                # リポジトリが空（初期コミットもない）場合などのエラー回避
                all_code_data += f"(コード取得スキップ: {e})\n"
                
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
    
    # Gemini APIの新しい呼び出し方
    response = client.models.generate_content(
        model='gemini-2.5-pro',
        contents=prompt
    )
    return response.text
    
if __name__ == "__main__":
    print("受講生コードを収集しています...")
    combined_code = collect_student_code()
    
    print("Geminiによるバッチ解析を実行中...")
    report = analyze_trends(combined_code)
    
    print("\n【解析レポート】\n")
    print(report)
