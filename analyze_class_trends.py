import os
import concurrent.futures
from google import genai
from github import Github, Auth

# ==========================================
# [設定値]
# ==========================================
ORG_NAME = "cac-it-training-2026"

# 理解度演習①
# ASSIGNMENT_PREFIX = "java-"  # 「java-ユーザー名」に対応
# BASE_DIR = "java_comprehension_exercises_volume1/src/" # 検索の起点となるディレクトリ

# 100本ノック
# ASSIGNMENT_PREFIX = "java100-github-classroom2nd-"  # 「java-ユーザー名」に対応
# BASE_DIR = "Java100_questions_cac2nd/src/" # 検索の起点となるディレクトリ

# 理解度演習②
# ASSIGNMENT_PREFIX = "java-comprehension-v2-"  # 「java-ユーザー名」に対応
# BASE_DIR = "java_comprehension_exercises_volume2_NO_NAME/src/" # 検索の起点となるディレクトリ

# ASSIGNMENT_PREFIX = "spring-practice-"  
# BASE_DIR = "spring_practice/src/" # 検索の起点となるディレクトリ

ASSIGNMENT_PREFIX = "shared-shop-app-"  
BASE_DIR = "shared_shop/src/" # 検索の起点となるディレクトリ

# --- 【追加】除外したいリポジトリ名の完全一致リスト ---
EXCLUDED_REPOS = [
    "shared-shop-app-shared-shop-z000",
    "shared-shop-app-shared-shop-akimoto",
    "shared-shop-app-shared-shop-z99nakayama"
]
# ------------------------------------------------------

BATCH_SIZE = 10  # 1回のGemini解析に渡す人数（トークン上限対策）

# 認証設定
github_token = os.getenv("ORG_READ_TOKEN")
gemini_key = os.getenv("GEMINI_API_KEY")

if not gemini_key or not github_token:
    print("❌ エラー: APIキーまたはGitHubトークンが読み込めません。")
    exit(1)

auth = Auth.Token(github_token)
g = Github(auth=auth)
client = genai.Client(api_key=gemini_key)

# 速度優先
MODEL_NAME = 'gemini-flash-latest' 

# ==========================================
# 1. GitHubからのデータ取得（並列処理で高速化）
# ==========================================
def fetch_single_repo(repo):
    """1つのリポジトリからコードを取得する関数"""
    # --- 【追加】除外リストに完全一致するリポジトリはスキップ ---
    if repo.name in EXCLUDED_REPOS:
        return None
    # ------------------------------------------------------------
    if not repo.name.startswith(ASSIGNMENT_PREFIX):
        return None
        
    student_id = repo.name.replace(ASSIGNMENT_PREFIX, "")
    student_data = f"\n\n====================\nStudent: {student_id}\n====================\n"
    
    try:
        branch = repo.default_branch
        tree = repo.get_git_tree(branch, recursive=True).tree
        
        found_files = False
        for item in tree:
            # --- 【追加】ルート直下の "repository" フォルダを丸ごと除外 ---
            if item.path.startswith("repository/"):
                continue
            # --------------------------------------------------------------
            if item.path.startswith(BASE_DIR) and item.path.endswith(".java"):
                
                # ファイルパスからファイル名だけを取り出す（例: "src/main/XxxTest.java" -> "XxxTest.java"）
                filename = item.path.split('/')[-1]
                
                # ファイル名に "Test" という文字列が含まれていれば除外
                if "Test" in filename:
                    continue

                file_content = repo.get_contents(item.path)
                code = file_content.decoded_content.decode('utf-8')

                # --- 【追加】巨大ファイル（5万文字以上）のスキップ安全装置 ---
                if len(code) > 50000:
                    student_data += f"\n--- File: {item.path} ---\n(※ファイルサイズが異常に大きいため、解析から除外しました。行数: {len(code.splitlines())})\n"
                    found_files = True
                    continue
                # --------------------------------------------------------------


                
                student_data += f"\n--- File: {item.path} ---\n{code}\n"
                found_files = True
                
        # 【修正ポイント】ファイルが見つからなかった場合は None を返して除外
        if not found_files:
            return None
            
    except Exception as e:
        # 初期コミットがない（完全な空リポジトリ）場合も除外
        return None
        
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
        
        # prompt_map = f"""
        # 以下のコードは、受講生120名のうちの一部のグループ（約{BATCH_SIZE}名）の提出物です。
        # このグループ内の「よくある間違い」「良い実装」「特筆すべき受講生ID」を簡潔に箇条書きで抽出してください。
        # また、各受講生の最終コミットクラスを抽出してください。(sss-tis　question01.Main.java)

        # チーム演習
        prompt_map = f"""
        以下のコードは、受講生120名のチーム演習（20グループ）の提出物です。
        このソースの24時間以内のコミットを見て「よくある間違い」「良い実装」「特筆すべきリポジトリ」を簡潔に箇条書きで抽出してください。
        また、コミット数が0または極端に少ないリポジトリがあれば挙げてください。
        
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

    # 【個人出力フォーマット】
    # 1. クラス全体の理解度サマリー（よくできている点）
    # 2. 全体に共通して見られる「アンチパターン」や「誤解」のトップ3
    # 3. 明日の講義で補足説明すべき重要な概念
    # 4. 特異な実装をしており、個別フォローが必要な受講生IDと理由（グループ分析で挙がっていれば）
    # 5. 受講生全員の最終進捗（最終コミットから算出する。省略せず全員分の進捗を出力する。ex sss-tis　question01.Main.java）

    
    prompt_reduce = f"""
    あなたはプロのJava技術研修講師です。
    以下は、120名の受講生を複数グループに分けて分析した「小レポート」の集まりです。
    これらを統合し、クラス全体を総括する最終レポートを以下のフォーマットで作成してください。
    
    【チーム演習出力フォーマット】
    0. 各チームのリポジトリごとの完成機能やソース品質（すべてのリポジトリをリポジトリ名の昇順で表示）
    1. 全体の理解度サマリー（よくできている点）
    2. 全体に共通して見られる「アンチパターン」や「誤解」のトップ3
    3. 特異な実装をしており、個別指摘が必要なリポジトリと理由（グループ分析で挙がっていれば）
    4. 24時間以内のコミット数や追加ステップが極端に少ないリポジトリ
    5. コミットコメントにfix: / add:　などの接頭辞がなく記述ルールが守られていないリポジトリ
    
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
