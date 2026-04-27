import os
import concurrent.futures
from google import genai
from github import Github, Auth

# ==========================================
# [設定値]
# ==========================================
ORG_NAME = "cac-it-training-2026"

# 理解度演習①
ASSIGNMENT_PREFIX = "java-"  # 「java-ユーザー名」に対応
BASE_DIR = "java_comprehension_exercises_volume1/src/" # 検索の起点となるディレクトリ

# 100本ノック
# ASSIGNMENT_PREFIX = "java100-github-classroom2nd-"  # 「java-ユーザー名」に対応
# BASE_DIR = "Java100_questions_cac2nd/src/" # 検索の起点となるディレクトリ

# ASSIGNMENT_PREFIX = "java-comprehension-v2-"  # 「java-ユーザー名」に対応
# BASE_DIR = "java_comprehension_exercises_volume2_NO_NAME/src/" # 検索の起点となるディレクトリ

BATCH_SIZE = 20  # 1回のGemini解析に渡す人数（トークン上限対策）

# 認証設定
github_token = os.getenv("ORG_READ_TOKEN")
gemini_key = os.getenv("GEMINI_API_KEY")

if not gemini_key or not github_token:
    print("❌ エラー: APIキーまたはGitHubトークンが読み込めません。")
    exit(1)

auth = Auth.Token(github_token)
g = Github(auth=auth)
client = genai.Client(api_key=gemini_key)

# 速度と精度を両立する 1.5-flash を推奨
MODEL_NAME = 'gemini-flash-latest' 

# ==========================================
# 1. GitHubからのデータ取得（並列処理で高速化）
# ==========================================
def fetch_single_repo(repo):
    """1つのリポジトリからコードを取得する関数"""
    if not repo.name.startswith(ASSIGNMENT_PREFIX):
        return None
        
    student_id = repo.name.replace(ASSIGNMENT_PREFIX, "")
    student_data = f"\n\n====================\nStudent: {student_id}\n====================\n"
    
    try:
        branch = repo.default_branch
        tree = repo.get_git_tree(branch, recursive=True).tree
        
        found_files = False
        for item in tree:
            # 指定フォルダ内の .java ファイルのみを抽出（不要ファイルを弾いてトークン節約）
            if item.path.startswith(BASE_DIR) and item.path.endswith(".java"):
                file_content = repo.get_contents(item.path)
                code = file_content.decoded_content.decode('utf-8')
                student_data += f"\n--- File: {item.path} ---\n{code}\n"
                found_files = True
                
        if not found_files:
            student_data += "(対象のJavaファイルがまだ作成されていません)\n"
            
    except Exception as e:
        student_data += f"(コード取得スキップ: {e})\n"
        
    return student_data

def collect_student_code_parallel():
    org = g.get_organization(ORG_NAME)
    repos = list(org.get_repos())
    
    print(f"📦 全 {len(repos)} 個のリポジトリからデータを並列取得します...")
    
    student_codes = []
    # 10スレッドで並列にGitHubからダウンロード（これで約10倍速になります）
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        results = executor.map(fetch_single_repo, repos)
        for res in results:
            if res:
                student_codes.append(res)
                
    return student_codes

# ==========================================
# 2. Geminiによる分割解析と統合（MapReduce）
# ==========================================
def analyze_in_batches(student_codes):
    sub_reports = []
    
    # リストを指定のバッチサイズ（20名）ずつに分割
    chunks = [student_codes[i:i + BATCH_SIZE] for i in range(0, len(student_codes), BATCH_SIZE)]
    print(f"\n🧠 取得したコードを {len(chunks)} 個のグループに分割して解析します...")
    
    # --- Mapフェーズ（グループごとの解析） ---
    for index, chunk in enumerate(chunks):
        print(f"  ⏳ グループ {index + 1}/{len(chunks)} を解析中...")
        chunk_text = "".join(chunk)
        
        prompt_map = f"""
        以下のコードは、受講生120名のうちの一部のグループ（約{BATCH_SIZE}名）の提出物です。
        このグループ内の「よくある間違い」「良い実装」「特筆すべき受講生ID」を簡潔に箇条書きで抽出してください。
        また、各受講生の最終コミットクラスを抽出してください。(田中次郎　question01.Main.java)
        
        【受講生コード】
        {chunk_text}
        """
        
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt_map
        )
        sub_reports.append(f"【グループ {index + 1} の分析結果】\n{response.text}\n")

    # --- Reduceフェーズ（全体の統合） ---
    print("\n📝 各グループの分析結果を統合し、最終レポートを作成します...")
    all_sub_reports_text = "\n".join(sub_reports)
    
    prompt_reduce = f"""
    あなたはプロのJava技術研修講師です。
    以下は、120名の受講生を複数グループに分けて分析した「小レポート」の集まりです。
    これらを統合し、クラス全体を総括する最終レポートを以下のフォーマットで作成してください。
    
    【出力フォーマット】
    1. クラス全体の理解度サマリー（よくできている点）
    2. 全体に共通して見られる「アンチパターン」や「誤解」のトップ3
    3. 明日の講義で補足説明すべき重要な概念
    4. 特異な実装をしており、個別フォローが必要な受講生IDと理由（グループ分析で挙がっていれば）
    5. 受講生全員の最終進捗（最終コミットから算出する）
    
    【各グループの小レポート】
    {all_sub_reports_text}
    """
    
    final_response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt_reduce
    )
    return final_response.text

# ==========================================
# 実行メイン
# ==========================================
if __name__ == "__main__":
    import time
    start_time = time.time()
    
    # 1. データの収集
    codes_list = collect_student_code_parallel()
    
    # 2. データの解析
    final_report = analyze_in_batches(codes_list)
    
    # 3. 結果出力
    print("\n" + "="*40)
    print("✨ 【最終解析レポート】 ✨")
    print("="*40 + "\n")
    print(final_report)
    
    elapsed_time = time.time() - start_time
    print(f"\n⏱️ 処理完了: 約 {int(elapsed_time // 60)} 分 {int(elapsed_time % 60)} 秒")
