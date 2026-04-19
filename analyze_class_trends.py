import os
import google.generativeai as genai
from github import Github

# 設定値（ここを変更しました）
ORG_NAME = "cac-it-training-2026"
ASSIGNMENT_PREFIX = "java-"  # 「java-ユーザー名」に対応
BASE_DIR = "java_comprehension_exercises_volume1/src/" # 検索の起点となるディレクトリ

# 認証設定
github_token = os.getenv("ORG_READ_TOKEN")
gemini_key = os.getenv("GEMINI_API_KEY")

g = Github(github_token)
genai.configure(api_key=gemini_key)
model = genai.GenerativeModel('gemini-2.5-pro')

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
    # プロンプト部分は前回と同じでOKです
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
