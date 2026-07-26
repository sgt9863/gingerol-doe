"""build_stlite.py — Streamlit アプリを stlite（ブラウザ内 Python）用の単一 HTML に固める

    python tools/build_stlite.py            # → docs/app.html を生成

生成した HTML はダブルクリックで開くだけで動く（Python もサーバーも不要）。
中身は stlite = Pyodide(WebAssembly) 上で本物の Streamlit を動かす仕組みで、
app.py・scripts/*.py・config・デモデータを JSON として HTML に埋め込む。

初回起動時だけ CDN から stlite / Pyodide / 各パッケージを取得する（以降はブラウザキャッシュ）。

依存パッケージの入手先（2種類ある）:
  prebuilt … Pyodide に同梱。numpy / pandas / scipy / statsmodels / matplotlib / pyyaml
  micropip … PyPI から取得する純 Python パッケージ。plotly / openpyxl
  kaleido は WebAssembly では動かない（Chrome が要る）ため、GIF 書き出しは自動的に非表示。
  → app.py 側の HAS_KALEIDO で分岐しているので、コードは通常環境と共通のまま。
"""

import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

STLITE_VERSION = "1.8.1"          # @stlite/browser のバージョン（Streamlit 1.57 / Python 3.13 同梱）
OUT_PATH = os.path.join(ROOT, "docs", "app.html")

# Pyodide に同梱されているもの（micropip で PyPI を見に行かせない）
PREBUILT = ["numpy", "pandas", "scipy", "statsmodels", "matplotlib", "pyyaml"]
# PyPI から取る純 Python パッケージ
REQUIREMENTS = ["plotly", "openpyxl"]

# 仮想ファイルシステムに置くファイル（リポジトリ相対パス → アプリ内パス）
FILE_MAP = {
    "app.py": "app.py",
    "scripts/01_model.py": "scripts/01_model.py",
    "scripts/02_design.py": "scripts/02_design.py",
    "scripts/03_fit.py": "scripts/03_fit.py",
    "scripts/04_optimize.py": "scripts/04_optimize.py",
    "scripts/05_designspace.py": "scripts/05_designspace.py",
    "scripts/06_quadratic.py": "scripts/06_quadratic.py",
    "config.example.yaml": "config.example.yaml",
    "data/demo_runs.csv": "data/demo_runs.csv",
    ".streamlit/config.toml": ".streamlit/config.toml",
}


def collect_files():
    """埋め込むファイルを読み込む。無いものは黙って飛ばさず、必須は例外にする。"""
    files = {}
    for src, dest in FILE_MAP.items():
        path = os.path.join(ROOT, src)
        if not os.path.exists(path):
            if src == ".streamlit/config.toml":       # テーマ設定は無くても動く
                continue
            raise FileNotFoundError(f"必要なファイルがありません: {src}")
        with open(path, encoding="utf-8") as f:
            files[dest] = f.read()
    return files


def js_json(obj):
    """JS に安全に埋め込める JSON 文字列。
    "<" をすべて \\u003c にする（"</script>" や "<!--" で HTML パーサが script を
    途中終了するのを防ぐ）。\\u003c は JSON としても JS としても正しいエスケープなので、
    値は元のまま・往復検証もできる。"""
    return json.dumps(obj, ensure_ascii=False).replace("<", "\\u003c")


def js_files_literal(files):
    """埋め込むファイル群を「1ソース行 = HTML 1行」の JS リテラルにする。

    全部を1行の JSON にすると 15 万文字の1行になり、GitHub 上で読めず
    git の差分も「1行まるごと変更」になってしまう。そこで各ファイルを
    行ごとの配列にして .join("\\n") で復元する形にする:

        "app.py": [
          "1行目",
          "2行目"
        ].join("\\n"),

    元の内容は完全に復元される（末尾改行も配列末尾の空文字として保持）。"""
    blocks = []
    for path, content in files.items():
        lines = content.split("\n")           # join("\n") で元に戻る（末尾改行も保持）
        body = ",\n".join("    " + js_json(line) for line in lines)
        blocks.append(f'  {js_json(path)}: [\n{body}\n  ].join("\\n")')
    return "{\n" + ",\n".join(blocks) + "\n}"


def parse_files_literal(html):
    """js_files_literal が書いた形を読み戻す（自己検査用）。
    各配列要素はちょうど1物理行に収まる（改行は \\n にエスケープ済み）ので行単位で復元できる。"""
    out, cur, path = {}, None, None
    for line in html.split("\n"):
        st = line.strip()
        if cur is None:
            m = re.match(r'^("(?:[^"\\]|\\.)*")\s*:\s*\[$', st)
            if m:
                path, cur = json.loads(m.group(1)), []
        elif st.startswith("].join("):
            out[path] = "\n".join(cur)
            cur, path = None, None
        else:
            cur.append(json.loads(st.rstrip(",")))
    return out


# 注意: このテンプレートは str.replace() で穴埋めする（str.format() ではない）。
# 波括弧は CSS / JS のものをそのまま書く（二重化しない）。
HTML = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HPLC デザインスペース最適化</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@stlite/browser@__VER__/build/stlite.css">
<style>
  html, body { margin: 0; height: 100%; }
  #boot {
    position: fixed; inset: 0; display: grid; place-content: center; gap: .9rem;
    font-family: system-ui, -apple-system, "Hiragino Sans", "Noto Sans JP", sans-serif;
    color: #16232b; background: #f7f9fa; text-align: center; padding: 2rem; z-index: 9;
  }
  @media (prefers-color-scheme: dark) {
    #boot { color: #e6edf0; background: #0e1518; }
  }
  #boot h1 { margin: 0; font-size: 1.2rem; font-weight: 650; letter-spacing: -.01em; }
  #boot p { margin: 0; font-size: .88rem; opacity: .72; line-height: 1.8; }
  #boot .bar {
    width: 220px; height: 3px; margin: 0 auto; border-radius: 3px; overflow: hidden;
    background: rgba(13,148,136,.18);
  }
  #boot .bar i {
    display: block; width: 40%; height: 100%; border-radius: 3px;
    background: linear-gradient(90deg, #0d9488, #0891b2); animation: slide 1.3s ease-in-out infinite;
  }
  @keyframes slide { 0% { transform: translateX(-100%); } 100% { transform: translateX(250%); } }
  @media (prefers-reduced-motion: reduce) { #boot .bar i { animation: none; width: 100%; } }
</style>
</head>
<body>
<div id="boot">
  <h1>HPLC デザインスペース最適化</h1>
  <div class="bar"><i></i></div>
  <p>ブラウザ内で Python を準備しています。<br>
     初回だけ数十秒〜数分かかります（2 回目以降はキャッシュから高速に起動）。</p>
</div>
<div id="root"></div>
<script type="module">
import { mount } from "https://cdn.jsdelivr.net/npm/@stlite/browser@__VER__/build/stlite.js";

const files = __FILES__;

mount({
  entrypoint: "app.py",
  prebuiltPackageNames: __PREBUILT__,
  requirements: __REQS__,
  files,
}, document.getElementById("root"));

// Streamlit の中身が描画されたらローディング表示を消す
const boot = document.getElementById("boot");
const root = document.getElementById("root");
const obs = new MutationObserver(() => {
  if (root.querySelector('[data-testid="stAppViewContainer"], .stApp')) {
    boot.remove();
    obs.disconnect();
  }
});
obs.observe(root, { childList: true, subtree: true });
</script>
</body>
</html>
"""


def self_check(html, files):
    """生成物の自己検査。壊れた HTML を出荷しないための最低限の関門。
    （テンプレートの穴埋めミスで JS が構文エラーになる事故が実際にあったため）"""
    skeleton = html.split("const files = ")[0] + html.split(";\n\nmount(", 1)[1]
    assert "{{" not in skeleton, "テンプレートに二重波括弧が残っている（JSが壊れる）"
    assert 'import { mount }' in html, "mount の import が壊れている"
    assert html.count("</script>") == 1, "埋め込み内容が script を途中で閉じている"

    # 埋め込んだ内容が元ファイルと完全一致するか（読み戻して比較）
    back = parse_files_literal(html)
    assert set(back) == set(files), f"ファイル一覧が違う: {set(files) ^ set(back)}"
    for dest, content in back.items():
        assert content == files[dest], f"埋め込み内容が元と違う: {dest}"

    # node があれば「構文チェック」＋「実際に評価して値が元と一致するか」まで見る。
    # 配列 + join("\n") で組み立てているので、構文だけでなく実行結果の確認に意味がある。
    import shutil, subprocess, tempfile, re as _re
    if shutil.which("node"):
        js = _re.search(r'<script type="module">(.*?)</script>', html, _re.S).group(1)
        js = _re.sub(r'^import .*?;$', 'const mount=()=>{};', js, count=1, flags=_re.M)
        with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False, encoding="utf-8") as t:
            t.write(js)
        r = subprocess.run(["node", "--check", t.name], capture_output=True, text=True)
        os.unlink(t.name)
        assert r.returncode == 0, f"JS 構文エラー: {r.stderr[:300]}"

        # files だけを取り出して評価し、JSON にして Python 側と突き合わせる
        lit = html.split("const files = ", 1)[1].rsplit(";\n\nmount(", 1)[0]
        with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False, encoding="utf-8") as t:
            t.write(f"const files = {lit};\nconsole.log(JSON.stringify(files));\n")
        r = subprocess.run(["node", t.name], capture_output=True, text=True)
        os.unlink(t.name)
        assert r.returncode == 0, f"JS 実行エラー: {r.stderr[:300]}"
        evaluated = json.loads(r.stdout)
        assert evaluated == files, "JS が組み立てた内容が元ファイルと一致しない"
        print("  自己検査: 波括弧・往復一致・JS構文・JS評価結果の一致 すべて OK")
    else:
        print("  自己検査: 波括弧・往復一致 OK（node が無いので JS 検査はスキップ）")


def build():
    files = collect_files()
    html = (HTML
            .replace("__VER__", STLITE_VERSION)
            .replace("__FILES__", js_files_literal(files))
            .replace("__PREBUILT__", js_json(PREBUILT))
            .replace("__REQS__", js_json(REQUIREMENTS)))
    self_check(html, files)
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    total = sum(len(v) for v in files.values())
    print(f"生成: {os.path.relpath(OUT_PATH, ROOT)}  "
          f"({len(html)/1024:.0f} KB / 埋め込み {len(files)} ファイル・{total/1024:.0f} KB)")
    for name in files:
        print(f"   - {name}")
    return OUT_PATH


if __name__ == "__main__":
    build()
