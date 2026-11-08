# VERSION: CLEAN-V171-DAILY-MEDAL-POPUP

CHOKOMANA_SETUP_SQL = "-- Project kotoba_app (keewulninyoeylgflshb), existing common schema checked 2026-11-08 JST.\n-- Add only the missing soroban writer. Do not recreate tables or alter existing RLS/GRANTs.\nbegin;\ncreate or replace function public.chokomana_append_soroban_events_v1(p_device_hash text,p_events jsonb)\nreturns jsonb language plpgsql security invoker set search_path='' as $$\ndeclare v_profile text;v jsonb;r public.chokomana_learning_events;stored jsonb;ids jsonb:='[]';\nbegin\n if p_device_hash !~ '^[a-f0-9]{64}$' then raise exception 'invalid device proof';end if;\n select profile_id::text into v_profile from public.chokomana_device_links where device_hash=p_device_hash and source_app='soroban';\n if v_profile is null then raise exception 'unverified profile' using errcode='42501';end if;\n if jsonb_typeof(p_events)<>'array' or jsonb_array_length(p_events)>100 or pg_column_size(p_events)>1048576 then raise exception 'invalid_batch';end if;\n for v in select value from jsonb_array_elements(p_events) loop\n  if v->>'profile_id' is distinct from v_profile or v->>'source_app' is distinct from 'soroban' then raise exception 'event owner mismatch' using errcode='42501';end if;\n  if (v->>'schema_version')::int<>1 or coalesce(v->>'event_hash','') !~ '^[a-f0-9]{64}$' then raise exception 'invalid schema or hash';end if;\n  r:=jsonb_populate_record(null::public.chokomana_learning_events,v);r.received_at:=now();\n  insert into public.chokomana_learning_events select r.* on conflict(event_id) do nothing;\n  select to_jsonb(e)-'received_at' into stored from public.chokomana_learning_events e where e.event_id=r.event_id;\n  if stored is distinct from to_jsonb(r)-'received_at' then raise exception 'event_id_content_conflict' using errcode='23505';end if;\n  ids:=ids||jsonb_build_array(r.event_id);\n end loop;\n return jsonb_build_object('acked',ids);\nend $$;\nrevoke all on function public.chokomana_append_soroban_events_v1(text,jsonb) from public,anon,authenticated;\ngrant execute on function public.chokomana_append_soroban_events_v1(text,jsonb) to service_role;\ncommit;\n"
CHOKOMANA_SPEC = 'ちょこまな そろばん ver.167 接続仕様・設定手順\n仕様ID chokomana.learning.v1 / schema_version=1\n対象 GitHub lstm500/soroban の app.py。取得時 HEAD cbad7f0d57db60147a773b9f83638c76c518aa2d、CLEAN-V163-STAMP-RECEIPTS。\n今回の変更: 追記型学習ログ、教材台帳、安全な既存起動チケット方式への識別接続。既存の問題・採点・音声・メダル・履歴の保存先は維持。\n最新の追加仕様に従い、共通時間の単位は整数ミリ秒。以前の依頼の「秒」を共通DBの列として併設しない。\n\n1. 配置と設定の実行順\n(1) このファイルは app.py_ver.167.py。配布物はこの単独Pythonのみ。\n    python app.py_ver.167.py --chokomana-sql > chokomana_learning_v1.sql\n    python app.py_ver.167.py --chokomana-spec > chokomana_spec.txt\n    python app.py_ver.167.py --chokomana-consumer > chokomana_consumer.py\n    python app.py_ver.167.py --chokomana-catalog > chokomana_catalog.json\n    python app.py_ver.167.py --chokomana-sample > chokomana_sample_simulated.json\n    これらのコマンドはStreamlitを起動せず、追加ライブラリを必要としない。\n(2) SQL Editor: プロジェクト kotoba_app / keewulninyoeylgflshb でSQL内容を確認して実行。\n    現在、共通台帳・イベントテーブルは作成済み。この版のSQLは不足していたそろばん専用追記RPCだけを追加する。テーブル・索引・RLS・既存テーブルのGRANTは変更しない。\n    chokomana_stamps、chocomana_state、geometry_attempts_v1、launch_tickets、device_linksは再作成・権限変更しない。\n    既存に同名で異なる構造が生じた場合は適用を止め、共通仕様との互換性を確認すること。\n    166の専用RPCは実DBへ追加済み。未連携端末の拒否を実DBで確認した。実プレイの保存成功はまだ未確認。\n(3) Streamlit Secrets: 既存 SUPABASE_URL、SUPABASE_SERVICE_ROLE_KEY をそのまま使用。\n    SUPABASE_URL は https://keewulninyoeylgflshb.supabase.co。\n    新規 CHOKOMANA_APP_URL="https://<このそろばんアプリのURL>" を設定。メニュー台帳のlaunch_url用。\n    URL未設定時は空文字を返し、直接起動可能とはしない。URLに認証情報・起動チケットを含めない。\n    CHOCOMANA_PROFILE_IDはこの版では使用しない。共有の固定プロフィールへは保存しない。\n(4) GitHubの対象ファイルを app.py にリネームして更新し、従来の方式で起動。リポジトリへのpush・デプロイは未実施。\n(5) 統合アプリから soroban 用 cm_launch チケット付きリンクで開く。普通に直接開くと、未連携でも学習・ローカル記録は続く。\n\n2. 検証済みの既存識別との対応\nDBにはchokomana_launch_tickets(ticket_hash,profile_id UUID,source_app,expires_at,used_at)と\nchokomana_device_links(device_hash,source_app,profile_id UUID)が存在する。いずれもRLS有効、service_roleのみの既存権限。\n参照した chokomana_guest_ver03 の統合アプリは匿名Authの本人IDを検証して一度限りのチケットを発行する。\n子アプリのサーバーがソース=soroban、有効期限内、未使用のチケットを条件付きPATCHで原子的に消費する。\n256bitのランダムな端末用Bearer値を、このアプリのlocalStorageの既存キー chokomana_device_identity_v1_soroban に保持。\nDBにはSHA256(\'soroban:\'+Bearer)だけを保存する。生BearerはURL・学習イベント・操作ログには入れない。\n毎回の保存でサーバーが対応表を確認し、profile_idを照合する。raw profile_idクエリは本人確認に使わない。\n無効・再利用チケットだけで別ブラウザに本人IDを渡さない。サービスキーはPythonサーバーだけで使用。\n別ドメインのlocalStorageは共有しない。共通化は起動チケットによる対応付けで行う。\n共通ID未確定のイベントはprofile_id=null、local_learner_id付きで端末に保持し、共有DBに送らない。\n後から別の子のIDが確定しても、既存の未連携履歴をその子へ自動統合しない。\n同じブラウザの子を切り替える場合、統合側がその子の検証済みIDで新しいチケットを発行する必要がある。\n参照版の統合アプリは匿名利用者をブラウザ単位で復元する方式であり、子ども選択画面を今回追加していない。\n現在の運用で同一端末の複数児を分離する方法は、子ごとに別のブラウザプロフィールを使うこと。\nブラウザ変更・データ削除・別端末では自動復元できない。統合側の元匿名セッションを復元して再起動チケットを発行する対応が必要。\n匿名Authの有効化は統合アプリ側で必要。そろばん側では新しい匿名ユーザーを勝手に作成せず、未連携を表示する。\n\n3. 共通正本と取得方法\n正本テーブル名は全アプリ共通で、今回そろばん専用の詳細履歴テーブルは作らない。\nchokomana_learning_catalog:\n  schema_version integer=1, source_app text, entry_type menu/skill/question,\n  entry_id text, content_version text, payload JSONB, published_at timestamptz(サーバー生成)。\n  PK=(source_app,entry_type,entry_id,content_version)。\n  menu/skillはauthenticatedへSELECT可。正解を含むquestion行は公開SELECT不可。\nchokomana_learning_events:\n  schema_version integer=1,event_id UUID PK,profile_id text,source_app text,\n  app_version text,content_version text,attempt_id UUID,occurrence_id UUID/null,\n  question_id text/null,segment_id UUID,sequence integer>0,occurred_at timestamptz UTC,\n  received_at timestamptz(サーバー生成),event_type text,payload JSONB。\n  UNIQUE(segment_id,sequence)。同じevent_idで異なる内容を再送するとRPCが拒否する。\n  全日時の送信形式はUTC ISO8601 Z付き。全共通時間は整数ms、未取得はnull。\n  authenticatedはprofile_id=auth.uid()::textの行だけSELECT可。anonのSELECT、クライアントの書込は不可。\n  強いサーバー権限で書く前にも端末との検証済み対応を照合する。\n保存経路: 端末の永続outbox → Streamlitコンポーネント → Python検証 → 追記RPC。\n  RPC chokomana_append_soroban_events_v1(p_device_hash text,p_events JSONB) はservice_roleだけ実行可、SECURITY INVOKER。\n統合側は自身の匿名Auth JWTと公開キーで次を取得する。\n  /rest/v1/chokomana_learning_catalog?entry_type=in.(menu,skill)&source_app=eq.soroban\n  /rest/v1/chokomana_learning_events?profile_id=eq.<本人UUID>&source_app=eq.soroban&order=segment_id,sequence\n  /rest/v1/chokomana_stamps?profile_id=eq.<本人UUID>&source_app=eq.soroban\n  大量履歴はevent_idを保ったままページングする。RLSをservice_roleで代用して全件配布しない。\n統合側の現行参照版はスタンプの取得・読み上げまで。台帳・イベントの取得・集計・計画生成は未実装で今回の対象外。\nsource_app=\'soroban\'固定。ファイル名app.pyは識別子ではない。\n\n4. 教材と技能の対応\n教材版 soroban-material-167: 167ではbs2x4の開始数を10〜99へ変更。その他の出題・採点定義は従来どおり。アプリ版は164。\n台帳は既存の計算25、補数6、九九5、暗算3、珠の動きの学習18、段別読み上げ9の合計66メニュー。\n固定教材・技能の詳細な対応は --chokomana-catalog で出力する。\n計算: soroban:calculation:<ba1..ba5x4,bs1..bs5x4,mm1..mm3,md1..md3,a1..a3>\n  技能 soroban:add/sub/mul/div。上級の複合問題は式の演算に対応する複数タグを保持。\n  補習・苦手克服は既存メニューとassignment_contextから mode=drill/review、trigger=remedialで区別。\n補数: soroban:hosu:add|sub:1|2|3。\n  大問の技能はcomplement:add/sub、complement:5/10。substep_idで段階を分離。\n  5/10判断、補数回答、再回答、答えを示した操作案内、任意解説、できたの確認を別イベントにする。\n  できたは申告であり、手元の珠を実測した証拠ではない。\n九九: soroban:kuku:1..5、段別技能 soroban:kuku:1..9 と掛け算タグ。\n暗算: soroban:anzan:1..3、数列・項数・桁数・提示間隔・声入力設定を保持。\n珠の動き: soroban:tutorial:<既存lesson.id>、worked_example後の選択回答として記録。\n読み上げ: soroban:kuku:read:1..9。mode=reading_aloud、回答・正誤なし。スタンプは発行しない。\n技能ラベルやクリック数だけで習得判定をしない。複合問題の誤答原因を個別技能へ断定しない。\n難易度順位はprogression_group_id内のみで比較。対象年齢・未確認の前提技能はnull。\n各メニューの時間はprovisionalで算定式を明記。実測値のように扱わない。\nlaunch_urlからメニューを直接指定する新しい起動方式は追加しない。supports_direct_launch=false、選択手順を返す。\n生成問題は式・数値・演算順を正規化したquestion_id。別数値と同一式の再出題を区別。\n問題の教材スナップショットと正解台帳はサーバー用。固定の全生成問題を事前列挙せず、出題時に台帳へ追記。\n既存の過去履歴200件などは維持し、精密な新ログへ捏造変換しない。\n163版の途中再開データだけは元attempt_idを維持し、legacy_importで旧形式・欠損を明示する。\n完了済み過去履歴や旧未連携スタンプキューを別の子に自動ひも付けしない。既存スタンプを重複発行しない。\n\n5. イベント・時間・同期\n各大問の出題枠はoccurrence_id、補数の段階はsubstep_id、各提出はresponse_id。\n初回のresponse_submittedを後の正解で更新しない。同じ枠の入力し直しは同じoccurrence_id。\n新しいチャレンジのattempt_idは新UUID。再開時は同じID、新segment_id、sequenceはそのsegmentで単調増加。\n回答拒否の空欄はイベント上も誤答にしない。わからない・skipのUIは元アプリにないので追加しない。\n対応するresponse_status列挙値は受理するが、操作されていない事実を捏造しない。\n九九の自動時間切れはtimed_out、明示的移動はabandoned、突然閉じた場合はpauseまでで終了不明。\n最終結果だけで内面の理解・理由・実際の珠操作は判定しない。親の助力は未観測なのでnull。\n時間はperformance.nowで区切り、絶対時刻を区間に併記。入力前の思考、読み上げ、解説も実学習に含む。\n非表示・明示休憩・操作不能な待機は除外。無操作を理由に除外しない。\n非同期のログ送信中もアプリで学習可能なので、その通信をblocking_waitとして除外しない。\n問題提示までの分類できない待機、再読み込みの隙間、時計変更はunknown扱い。実測0と混ぜない。\n5秒ごとの安全な区切り、表示切替、回答、ヒント、非表示、pagehideで端末へ保存。\n他タブが同じ実施を持つ場合は端末leaseで所有者を識別し、非所有者は時間を加算しない。\n他アプリ・他タブも含む計画用時間は、profile_idごとの有効な絶対区間の和集合から算出する。\nattemptの合計や再送数を単純加算しない。日本時間0時で区間を分割する。\nブラウザの強制終了やOS停止で最後のチェックポイント以降を取得できないことがある。欠損を0としない。\n時計ずれの絶対時刻、物理そろばんの操作、画面外の保護者の支援は測定できない。\n送信は最大50イベント・約200KBの小バッチ。30秒の定期送信と区切り時。失敗時は待ち時間を増やし最大5分。\n同じevent_id、attempt_idで再送し、サーバーがACKしたイベントのみoutboxから削除。\nスタンプだけ失敗した場合、ACK済みのイベントを再発行せず、同じattempt_idでスタンプを再送。\noutboxはlocalStorage。未送信件数で切り捨てない。保存容量不足時は設定の接続状態欄に保存できない旨を表示。\nブラウザデータ削除、端末故障、保存拒否時の終了では未送信分を失う可能性がある。\nACK済みの正本はSupabase。端末の出力用キャッシュは最新実施と未送信分、ACKのIDのみ保持し、履歴本体を全件二重保存しない。\n設定不足・通信失敗でも学習を止めない。未連携・未送信を成功と表示しない。\nサービスキー、端末Bearer、認識候補全文、音声、動画、UI速度ログを学習イベントへ混ぜない。\n\n6. 集計定義・実データ出力\n同梱のconsumer参照実装 summarize(events,catalog) は計画や能力評価を行わない。\n初回正答率: 出題枠×小段階の最初のanswered/automatic/is_correct非nullのみ。\n自力初回: 上記から回答前に記録されたhint/解説/答え/見本ありを除外。記録されていない親の助力まで否定しない。\n支援後正解、再回答正解、skip/dont_know/timed_out、除外理由と対象件数を別々に返す。\n共通条件=本人×アプリ×技能×教材版×進級系列×難易度×評価方式×mode×入力・音声等の設定。\n初回正答率と生涯初見は別。生涯履歴が保証されないため生涯初見正答率はnull。\n技能の利用可能分母は台帳available_skill_ids、接触/回答の技能IDを返す。習得とは判定しない。\n後日の同一問題の成績・間隔、異なるquestion_idの成功数・日付・根拠イベントを返し、保持・転用の候補を再計算できる。\nメニュー×難易度×設定別に、有効な完了履歴の直近10件の中央値を計算。3件未満は measured_estimate_ms=null。\n観測中央値と仮設定は分離し、サンプル件数・品質・教材版を保持。再開欠損・時計ずれ・終了不明は目安時間の算定から除外。\n「できた」操作回数を能力点数に換算しない。理解済み・得意・苦手の断定やAI判定を追加しない。\n実データ出力: 学習アプリのiframeの開発者コンソールで window.__chokomanaExportSession() を実行。\n最新の実施1回を共通形式JSONでダウンロードする。引数に保存済みattempt_idも指定可（端末キャッシュ範囲内）。\n設定画面の「学習ログを出力」でも同じJSONを保存できる。既存のUI応答速度ログや動画ログとは別ファイル。\n--chokomana-sample は実際のJS処理を模擬入力で動かした試験例。test_fixture=trueであり、子どもの実履歴ではなく本番へ送信しない。\n\n7. 確認範囲\n模擬: 実際の埋め込みJSで通常25モードの共通開始処理、九九全5レベル、補数、暗算、再開・途中終了、珠の動きと読み上げ。\n  通常計算は代表モードba1で出題・採点・履歴・完了を実行。25モード全問を別々に回帰したという意味ではない。\n  補数の小問・解説、初回誤答→ヒント→再回答、端末保存失敗、未連携・別学習者、pagehide再開を確認。\n  時間試験の期待値: 実学習8000ms、非表示3000ms、明示休憩2000ms。JST跨ぎは前日5000ms・翌日3000ms。\n  イベント重複・逆順、同一ID異内容の拒否、初回成績不変、直近10件・3件未満の中央値、区間和集合を確認。\nローカルPGlite(PostgreSQL互換実行環境): SQL構文、追記RPC、RLS本人/別人、書込権限、正解台帳の非公開を確認。\nSupabase: 現在のテーブル・event_hash列・一意制約・権限を確認。そろばん用RPCを追加し、未検証端末の拒否を実DB確認。実プレイ由来のData API実保存は未確認。\n実ブラウザ/実機のマイク、実音声、実デプロイ環境での処理時間・UI表示は未確認。模擬音声APIによる回帰と区別する。\n他アプリ、統合側の詳細ログ読取・集計UI・今日やるリストは変更していない。\n\n166修正: 通常の次問表示をpage_reload再開として記録していた不具合を修正。segmentが変わった実再開時だけ記録する。catalogは既存INSERT/SELECT権限で動く重複無視とし、サーバーでevent_hash(SHA256)を付加する。\n実確認: app.pyを166へ更新→ちょこまなから起動→設定が接続済みであることを確認→通常チャレンジを1回完了→このチャットへ完了を知らせる。意図的な誤答を子どもの実成績へ混ぜない。\n'
CHOKOMANA_REFERENCE_PY = '"""Reference consumer for chokomana.learning.v1; no ability classification or planning.\nUse only RLS-filtered events for one verified learner. All durations are integer ms.\n"""\nimport collections,datetime,statistics,json\n\ndef summarize(events,catalog=None):\n    # event_id is the identity; conflicting contents are an error, never a second observation.\n    unique={}\n    for e in events:\n        key=e[\'event_id\']\n        if key in unique and unique[key]!=e:raise ValueError(\'event_id_content_conflict\')\n        unique[key]=e\n    rows=list(unique.values());presented={e[\'occurrence_id\']:e for e in rows if e[\'event_type\']==\'item_presented\'}\n    starts={e[\'attempt_id\']:e for e in rows if e[\'event_type\']==\'session_started\'}\n    ends={e[\'attempt_id\']:e for e in sorted(rows,key=lambda e:(e[\'occurred_at\'],e[\'segment_id\'],e[\'sequence\'])) if e[\'event_type\']==\'session_ended\'}\n    def date(s):return datetime.datetime.fromisoformat(s.replace(\'Z\',\'+00:00\'))\n    groups=collections.defaultdict(lambda:{\'first_correct\':0,\'first_total\':0,\'independent_correct\':0,\'independent_total\':0,\'excluded\':collections.Counter(),\'supported_correct\':0,\'retry_correct\':0,\'status\':collections.Counter(),\'evidence_event_ids\':[],\'question_ids\':set(),\'dates\':set(),\'retention\':[],\'observations\':[],\'contacts\':set(),\'answered\':set()})\n    cohorts={};occur_responses=collections.defaultdict(list)\n    for e in rows:\n        if e[\'event_type\']==\'response_submitted\':occur_responses[e[\'occurrence_id\']].append(e)\n    # One denominator per occurrence/substep. Parent-linked retries are not new first attempts.\n    for oid,item in presented.items():\n        ip=item[\'payload\'];start=starts.get(item[\'attempt_id\']);sp=start[\'payload\'] if start else {}\n        responses=sorted(occur_responses[oid],key=lambda e:e[\'payload\'][\'response_index\'])\n        steps=collections.defaultdict(list)\n        for r in responses:steps[r[\'payload\'].get(\'substep_id\')].append(r)\n        for skill in ip.get(\'skill_ids\',[]):\n            for substep,rr in steps.items():\n                first=rr[0];p=first[\'payload\'];\n                if p.get(\'skill_ids\') is not None and skill not in p[\'skill_ids\']:continue\n                settings=sp.get(\'settings_snapshot\',{})\n                condition=json.dumps({\'input_method\':p.get(\'input_method\'),\'settings\':settings},sort_keys=True)\n                key=(item[\'profile_id\'],item[\'source_app\'],skill,item[\'content_version\'],sp.get(\'progression_group_id\'),sp.get(\'difficulty_id\'),p.get(\'assessment_method\'),sp.get(\'mode\'),condition,substep)\n                g=groups[key];g[\'contacts\'].add(oid);g[\'answered\'].add(oid);g[\'status\'].update(r[\'payload\'][\'response_status\'] for r in rr)\n                if ip.get(\'parent_occurrence_id\') or ip.get(\'presentation_kind\')==\'retry\':g[\'excluded\'][\'parent_linked_retry\']+=1;continue\n                if p.get(\'response_status\')!=\'answered\':g[\'excluded\'][p.get(\'response_status\',\'unknown\')]+=1;continue\n                if p.get(\'assessment_method\')!=\'automatic\' or p.get(\'is_correct\') is None:g[\'excluded\'][\'non_objective_or_unscored\']+=1;continue\n                g[\'first_total\']+=1;g[\'first_correct\']+=int(p[\'is_correct\'])\n                support=p.get(\'support_before_response\');eligible=True\n                if not isinstance(support,dict) or support.get(\'hint_count\') is None:eligible=False;g[\'excluded\'][\'support_unknown\']+=1\n                elif support.get(\'hint_count\',0)>0 or any(support.get(k) for k in (\'explanation_seen\',\'answer_seen\',\'worked_example_seen\',\'parent_help\')) or ip.get(\'answer_exposed_before\'):\n                    eligible=False;g[\'excluded\'][\'support_before_first\']+=1\n                # parent_help=None means unobserved real-world help; do not claim physical independence.\n                if eligible:\n                    g[\'independent_total\']+=1;g[\'independent_correct\']+=int(p[\'is_correct\'])\n                    day=(date(first[\'occurred_at\'])+datetime.timedelta(hours=9)).date().isoformat()\n                    g[\'observations\'].append({\'day\':day,\'question_id\':item[\'question_id\'],\'family_id\':ip.get(\'question_family_id\'),\'correct\':p[\'is_correct\'],\'event_id\':first[\'event_id\'],\'related_material_id\':ip.get(\'related_material_id\')})\n                    if p[\'is_correct\']:g[\'question_ids\'].add(item[\'question_id\']);g[\'dates\'].add(day)\n                    elif len(ip.get(\'skill_ids\',[]))==1 or substep is not None:g[\'evidence_event_ids\'].append(first[\'event_id\'])\n                elif any(r[\'payload\'].get(\'is_correct\') for r in rr):g[\'supported_correct\']+=1;g[\'evidence_event_ids\'].append(first[\'event_id\'])\n                if any(r[\'payload\'].get(\'is_correct\') for r in rr[1:]):g[\'retry_correct\']+=1\n    def union(intervals):\n        intervals=sorted(intervals);merged=[]\n        for start,end in intervals:\n            if merged and start<=merged[-1][1]:merged[-1]=(merged[-1][0],max(end,merged[-1][1]))\n            else:merged.append((start,end))\n        return merged\n    by_profile=collections.defaultdict(list);attempt_intervals=collections.defaultdict(list);unknown=0\n    for e in rows:\n        if e[\'event_type\']!=\'time_interval_closed\':continue\n        p=e[\'payload\']\n        if p.get(\'active_ms\') is None or p.get(\'timing_quality\') not in (\'complete\',\'partial\'):\n            unknown+=1;continue\n        if p[\'active_ms\']<=0:continue\n        start,end=date(p[\'start_at\']),date(p[\'end_at\'])\n        # Only fully-active intervals have a reconstructable position for a union.\n        if abs((end-start).total_seconds()*1000-p[\'active_ms\'])>2:unknown+=1;continue\n        by_profile[e[\'profile_id\']].append((start,end));attempt_intervals[e[\'attempt_id\']].append((start,end))\n    daily={}\n    for profile,spans in by_profile.items():\n        days=collections.Counter()\n        for start,end in union(spans):\n            while start<end:\n                jst=start+datetime.timedelta(hours=9);boundary=datetime.datetime.combine(jst.date()+datetime.timedelta(days=1),datetime.time(tzinfo=datetime.timezone.utc))-datetime.timedelta(hours=9)\n                stop=min(end,boundary);days[jst.date().isoformat()]+=round((stop-start).total_seconds()*1000);start=stop\n        daily[profile]=dict(days)\n    durations=collections.defaultdict(list)\n    for aid,end in ends.items():\n        start=starts.get(aid)\n        if not start or end[\'payload\'][\'status\']!=\'completed\':continue\n        relevant=[e for e in rows if e[\'attempt_id\']==aid and e[\'event_type\']==\'time_interval_closed\']\n        if not relevant or any(e[\'payload\'].get(\'timing_quality\')!=\'complete\' or e[\'payload\'].get(\'active_ms\') is None for e in relevant):continue\n        if any(e[\'attempt_id\']==aid and e[\'event_type\']==\'session_resumed\' and e[\'payload\'].get(\'reason\')==\'page_reload\' for e in rows):continue\n        p=start[\'payload\'];condition=json.dumps(p.get(\'settings_snapshot\',{}),sort_keys=True)\n        key=(start[\'profile_id\'],start[\'source_app\'],p[\'menu_id\'],p[\'difficulty_id\'],start[\'content_version\'],condition)\n        ms=sum(round((b-a).total_seconds()*1000) for a,b in union(attempt_intervals[aid]))\n        if ms>0:durations[key].append((end[\'occurred_at\'],ms))\n    medians=[]\n    for key,items in durations.items():\n        recent=sorted(items,reverse=True)[:10];values=[v for _,v in recent]\n        medians.append({\'cohort\':list(key),\'sample_count\':len(values),\'observed_median_ms\':statistics.median(values),\'measured_estimate_ms\':statistics.median(values) if len(values)>=3 else None,\'estimate_sufficient\':len(values)>=3,\'basis\':\'measured\' if len(values)>=3 else \'insufficient\'})\n    out=[]\n    for key,g in groups.items():\n        observations=sorted(g.pop(\'observations\'),key=lambda x:x[\'day\']);last={};retention=[]\n        for o in observations:\n            previous=last.get(o[\'question_id\'])\n            if previous and previous[\'day\']<o[\'day\']:retention.append({\'event_id\':o[\'event_id\'],\'previous_event_id\':previous[\'event_id\'],\'day\':o[\'day\'],\'interval_days\':(datetime.date.fromisoformat(o[\'day\'])-datetime.date.fromisoformat(previous[\'day\'])).days,\'correct\':o[\'correct\']})\n            last[o[\'question_id\']]=o\n        g[\'retention\']=retention;g[\'transfer_distinct_question_count\']=len(g[\'question_ids\']);g[\'successful_days\']=sorted(g.pop(\'dates\'));g.pop(\'question_ids\')\n        g[\'contacted_occurrences\']=len(g.pop(\'contacts\'));g[\'answered_occurrences\']=len(g.pop(\'answered\'))\n        g[\'first_accuracy\']=g[\'first_correct\']/g[\'first_total\'] if g[\'first_total\'] else None;g[\'independent_first_accuracy\']=g[\'independent_correct\']/g[\'independent_total\'] if g[\'independent_total\'] else None\n        g[\'lifetime_first_accuracy\']=None;g[\'ability_label\']=None;g[\'cohort\']=list(key);g[\'period_observations\']=observations;out.append(g)\n    progress=[]\n    menu_rows=[c for c in (catalog or []) if c.get(\'entry_type\')==\'menu\']\n    for profile,source,version in sorted({(e[\'profile_id\'],e[\'source_app\'],e[\'content_version\']) for e in rows}):\n        available=set(s for c in menu_rows if c[\'source_app\']==source and c[\'content_version\']==version for s in c[\'payload\'].get(\'available_skill_ids\',[]))\n        contacted=set();answered=set()\n        for item in presented.values():\n            if (item[\'profile_id\'],item[\'source_app\'],item[\'content_version\'])!=(profile,source,version):continue\n            contacted.update(item[\'payload\'].get(\'skill_ids\',[]))\n            if occur_responses[item[\'occurrence_id\']]:answered.update(item[\'payload\'].get(\'skill_ids\',[]))\n        progress.append({\'profile_id\':profile,\'source_app\':source,\'content_version\':version,\'available_skill_count\':len(available) if catalog is not None else None,\'contacted_skill_ids\':sorted(contacted),\'answered_skill_ids\':sorted(answered),\'denominator_basis\':\'active_catalog_available_skill_ids\' if catalog is not None else \'unknown\'})\n    return {\'progress\':progress,\'specification_id\':\'chokomana.learning.v1\',\'groups\':out,\'daily_active_ms_union\':daily,\'duration_estimates\':medians,\'unknown_time_interval_count\':unknown,\'ended_attempt_count\':len(ends),\'end_unknown_attempt_ids\':sorted(set(starts)-set(ends)),\'note\':\'Independent means no app-recorded support, not proof that no adult helped. No ability classification. Reading-only contacts are in item_presented events; never in accuracy denominator.\'}\n'
CHOKOMANA_CATALOG_JSON = '[\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:calculation:ba1",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:calculation:ba1",\n      "label": "初級・足し算1｜1桁・繰り上がりなし",\n      "category_id": "calculation",\n      "category_label": "そろばん・計算",\n      "difficulty_id": "ba1",\n      "difficulty_label": "ba1",\n      "difficulty_order": 1,\n      "progression_group_id": "soroban:calculation:add",\n      "skill_ids": [\n        "soroban:add"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "challenge"\n      ],\n      "question_count_default": 12,\n      "question_count_options": [\n        4,\n        12\n      ],\n      "estimated_duration_ms": 300000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "チャレンジモード",\n        "初級・足し算1｜1桁・繰り上がりなし"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:add"\n      ],\n      "next_menu_ids": [\n        "soroban:calculation:ba2"\n      ]\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:calculation:ba2",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:calculation:ba2",\n      "label": "初級・足し算2｜1桁・繰り上がりあり",\n      "category_id": "calculation",\n      "category_label": "そろばん・計算",\n      "difficulty_id": "ba2",\n      "difficulty_label": "ba2",\n      "difficulty_order": 2,\n      "progression_group_id": "soroban:calculation:add",\n      "skill_ids": [\n        "soroban:add"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "challenge"\n      ],\n      "question_count_default": 12,\n      "question_count_options": [\n        4,\n        12\n      ],\n      "estimated_duration_ms": 300000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "チャレンジモード",\n        "初級・足し算2｜1桁・繰り上がりあり"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:add"\n      ],\n      "next_menu_ids": [\n        "soroban:calculation:ba2x4"\n      ]\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:calculation:ba2x4",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:calculation:ba2x4",\n      "label": "初級・足し算3｜1桁の数を4つ足す",\n      "category_id": "calculation",\n      "category_label": "そろばん・計算",\n      "difficulty_id": "ba2x4",\n      "difficulty_label": "ba2x4",\n      "difficulty_order": 3,\n      "progression_group_id": "soroban:calculation:add",\n      "skill_ids": [\n        "soroban:add"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "challenge"\n      ],\n      "question_count_default": 12,\n      "question_count_options": [\n        4,\n        12\n      ],\n      "estimated_duration_ms": 300000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "チャレンジモード",\n        "初級・足し算3｜1桁の数を4つ足す"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:add"\n      ],\n      "next_menu_ids": [\n        "soroban:calculation:ba3"\n      ]\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:calculation:ba3",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:calculation:ba3",\n      "label": "初級・足し算4｜2桁・繰り上がりなし",\n      "category_id": "calculation",\n      "category_label": "そろばん・計算",\n      "difficulty_id": "ba3",\n      "difficulty_label": "ba3",\n      "difficulty_order": 4,\n      "progression_group_id": "soroban:calculation:add",\n      "skill_ids": [\n        "soroban:add"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "challenge"\n      ],\n      "question_count_default": 12,\n      "question_count_options": [\n        4,\n        12\n      ],\n      "estimated_duration_ms": 300000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "チャレンジモード",\n        "初級・足し算4｜2桁・繰り上がりなし"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:add"\n      ],\n      "next_menu_ids": [\n        "soroban:calculation:ba4"\n      ]\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:calculation:ba4",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:calculation:ba4",\n      "label": "初級・足し算5｜2桁・繰り上がりあり",\n      "category_id": "calculation",\n      "category_label": "そろばん・計算",\n      "difficulty_id": "ba4",\n      "difficulty_label": "ba4",\n      "difficulty_order": 5,\n      "progression_group_id": "soroban:calculation:add",\n      "skill_ids": [\n        "soroban:add"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "challenge"\n      ],\n      "question_count_default": 12,\n      "question_count_options": [\n        4,\n        12\n      ],\n      "estimated_duration_ms": 300000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "チャレンジモード",\n        "初級・足し算5｜2桁・繰り上がりあり"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:add"\n      ],\n      "next_menu_ids": [\n        "soroban:calculation:ba4x4"\n      ]\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:calculation:ba4x4",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:calculation:ba4x4",\n      "label": "初級・足し算6｜2桁の数を4つ足す",\n      "category_id": "calculation",\n      "category_label": "そろばん・計算",\n      "difficulty_id": "ba4x4",\n      "difficulty_label": "ba4x4",\n      "difficulty_order": 6,\n      "progression_group_id": "soroban:calculation:add",\n      "skill_ids": [\n        "soroban:add"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "challenge"\n      ],\n      "question_count_default": 12,\n      "question_count_options": [\n        4,\n        12\n      ],\n      "estimated_duration_ms": 300000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "チャレンジモード",\n        "初級・足し算6｜2桁の数を4つ足す"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:add"\n      ],\n      "next_menu_ids": [\n        "soroban:calculation:ba5"\n      ]\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:calculation:ba5",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:calculation:ba5",\n      "label": "初級・足し算7｜3桁の足し算",\n      "category_id": "calculation",\n      "category_label": "そろばん・計算",\n      "difficulty_id": "ba5",\n      "difficulty_label": "ba5",\n      "difficulty_order": 7,\n      "progression_group_id": "soroban:calculation:add",\n      "skill_ids": [\n        "soroban:add"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "challenge"\n      ],\n      "question_count_default": 12,\n      "question_count_options": [\n        4,\n        12\n      ],\n      "estimated_duration_ms": 300000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "チャレンジモード",\n        "初級・足し算7｜3桁の足し算"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:add"\n      ],\n      "next_menu_ids": [\n        "soroban:calculation:ba5x4"\n      ]\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:calculation:ba5x4",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:calculation:ba5x4",\n      "label": "初級・足し算8｜3桁の数を4つ足す",\n      "category_id": "calculation",\n      "category_label": "そろばん・計算",\n      "difficulty_id": "ba5x4",\n      "difficulty_label": "ba5x4",\n      "difficulty_order": 8,\n      "progression_group_id": "soroban:calculation:add",\n      "skill_ids": [\n        "soroban:add"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "challenge"\n      ],\n      "question_count_default": 12,\n      "question_count_options": [\n        4,\n        12\n      ],\n      "estimated_duration_ms": 300000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "チャレンジモード",\n        "初級・足し算8｜3桁の数を4つ足す"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:add"\n      ],\n      "next_menu_ids": []\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:calculation:bs1",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:calculation:bs1",\n      "label": "初級・引き算1｜1桁・繰り下がりなし",\n      "category_id": "calculation",\n      "category_label": "そろばん・計算",\n      "difficulty_id": "bs1",\n      "difficulty_label": "bs1",\n      "difficulty_order": 1,\n      "progression_group_id": "soroban:calculation:sub",\n      "skill_ids": [\n        "soroban:sub"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "challenge"\n      ],\n      "question_count_default": 12,\n      "question_count_options": [\n        4,\n        12\n      ],\n      "estimated_duration_ms": 300000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "チャレンジモード",\n        "初級・引き算1｜1桁・繰り下がりなし"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:sub"\n      ],\n      "next_menu_ids": [\n        "soroban:calculation:bs2"\n      ]\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:calculation:bs2",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:calculation:bs2",\n      "label": "初級・引き算2｜1桁を引く・繰り下がりあり",\n      "category_id": "calculation",\n      "category_label": "そろばん・計算",\n      "difficulty_id": "bs2",\n      "difficulty_label": "bs2",\n      "difficulty_order": 2,\n      "progression_group_id": "soroban:calculation:sub",\n      "skill_ids": [\n        "soroban:sub"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "challenge"\n      ],\n      "question_count_default": 12,\n      "question_count_options": [\n        4,\n        12\n      ],\n      "estimated_duration_ms": 300000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "チャレンジモード",\n        "初級・引き算2｜1桁を引く・繰り下がりあり"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:sub"\n      ],\n      "next_menu_ids": [\n        "soroban:calculation:bs2x4"\n      ]\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:calculation:bs2x4",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:calculation:bs2x4",\n      "label": "初級・引き算3｜2桁から1桁の数を3回引く",\n      "category_id": "calculation",\n      "category_label": "そろばん・計算",\n      "difficulty_id": "bs2x4",\n      "difficulty_label": "bs2x4",\n      "difficulty_order": 3,\n      "progression_group_id": "soroban:calculation:sub",\n      "skill_ids": [\n        "soroban:sub"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "challenge"\n      ],\n      "question_count_default": 12,\n      "question_count_options": [\n        4,\n        12\n      ],\n      "estimated_duration_ms": 300000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "チャレンジモード",\n        "初級・引き算3｜2桁から1桁の数を3回引く"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:sub"\n      ],\n      "next_menu_ids": [\n        "soroban:calculation:bs3"\n      ]\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:calculation:bs3",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:calculation:bs3",\n      "label": "初級・引き算4｜2桁・繰り下がりなし",\n      "category_id": "calculation",\n      "category_label": "そろばん・計算",\n      "difficulty_id": "bs3",\n      "difficulty_label": "bs3",\n      "difficulty_order": 4,\n      "progression_group_id": "soroban:calculation:sub",\n      "skill_ids": [\n        "soroban:sub"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "challenge"\n      ],\n      "question_count_default": 12,\n      "question_count_options": [\n        4,\n        12\n      ],\n      "estimated_duration_ms": 300000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "チャレンジモード",\n        "初級・引き算4｜2桁・繰り下がりなし"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:sub"\n      ],\n      "next_menu_ids": [\n        "soroban:calculation:bs4"\n      ]\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:calculation:bs4",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:calculation:bs4",\n      "label": "初級・引き算5｜2桁・繰り下がりあり",\n      "category_id": "calculation",\n      "category_label": "そろばん・計算",\n      "difficulty_id": "bs4",\n      "difficulty_label": "bs4",\n      "difficulty_order": 5,\n      "progression_group_id": "soroban:calculation:sub",\n      "skill_ids": [\n        "soroban:sub"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "challenge"\n      ],\n      "question_count_default": 12,\n      "question_count_options": [\n        4,\n        12\n      ],\n      "estimated_duration_ms": 300000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "チャレンジモード",\n        "初級・引き算5｜2桁・繰り下がりあり"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:sub"\n      ],\n      "next_menu_ids": [\n        "soroban:calculation:bs4x4"\n      ]\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:calculation:bs4x4",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:calculation:bs4x4",\n      "label": "初級・引き算6｜2桁の数を4つ使う引き算",\n      "category_id": "calculation",\n      "category_label": "そろばん・計算",\n      "difficulty_id": "bs4x4",\n      "difficulty_label": "bs4x4",\n      "difficulty_order": 6,\n      "progression_group_id": "soroban:calculation:sub",\n      "skill_ids": [\n        "soroban:sub"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "challenge"\n      ],\n      "question_count_default": 12,\n      "question_count_options": [\n        4,\n        12\n      ],\n      "estimated_duration_ms": 300000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "チャレンジモード",\n        "初級・引き算6｜2桁の数を4つ使う引き算"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:sub"\n      ],\n      "next_menu_ids": [\n        "soroban:calculation:bs5"\n      ]\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:calculation:bs5",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:calculation:bs5",\n      "label": "初級・引き算7｜3桁の引き算",\n      "category_id": "calculation",\n      "category_label": "そろばん・計算",\n      "difficulty_id": "bs5",\n      "difficulty_label": "bs5",\n      "difficulty_order": 7,\n      "progression_group_id": "soroban:calculation:sub",\n      "skill_ids": [\n        "soroban:sub"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "challenge"\n      ],\n      "question_count_default": 12,\n      "question_count_options": [\n        4,\n        12\n      ],\n      "estimated_duration_ms": 300000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "チャレンジモード",\n        "初級・引き算7｜3桁の引き算"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:sub"\n      ],\n      "next_menu_ids": [\n        "soroban:calculation:bs5x4"\n      ]\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:calculation:bs5x4",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:calculation:bs5x4",\n      "label": "初級・引き算8｜3桁から2桁を4回引く",\n      "category_id": "calculation",\n      "category_label": "そろばん・計算",\n      "difficulty_id": "bs5x4",\n      "difficulty_label": "bs5x4",\n      "difficulty_order": 8,\n      "progression_group_id": "soroban:calculation:sub",\n      "skill_ids": [\n        "soroban:sub"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "challenge"\n      ],\n      "question_count_default": 12,\n      "question_count_options": [\n        4,\n        12\n      ],\n      "estimated_duration_ms": 300000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "チャレンジモード",\n        "初級・引き算8｜3桁から2桁を4回引く"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:sub"\n      ],\n      "next_menu_ids": []\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:calculation:mm1",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:calculation:mm1",\n      "label": "中級・掛け算1｜1桁×1桁",\n      "category_id": "calculation",\n      "category_label": "そろばん・計算",\n      "difficulty_id": "mm1",\n      "difficulty_label": "mm1",\n      "difficulty_order": 1,\n      "progression_group_id": "soroban:calculation:mul",\n      "skill_ids": [\n        "soroban:mul"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "challenge"\n      ],\n      "question_count_default": 12,\n      "question_count_options": [\n        4,\n        12\n      ],\n      "estimated_duration_ms": 300000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "チャレンジモード",\n        "中級・掛け算1｜1桁×1桁"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:mul"\n      ],\n      "next_menu_ids": [\n        "soroban:calculation:mm2"\n      ]\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:calculation:mm2",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:calculation:mm2",\n      "label": "中級・掛け算2｜2桁×1桁",\n      "category_id": "calculation",\n      "category_label": "そろばん・計算",\n      "difficulty_id": "mm2",\n      "difficulty_label": "mm2",\n      "difficulty_order": 2,\n      "progression_group_id": "soroban:calculation:mul",\n      "skill_ids": [\n        "soroban:mul"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "challenge"\n      ],\n      "question_count_default": 12,\n      "question_count_options": [\n        4,\n        12\n      ],\n      "estimated_duration_ms": 300000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "チャレンジモード",\n        "中級・掛け算2｜2桁×1桁"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:mul"\n      ],\n      "next_menu_ids": [\n        "soroban:calculation:mm3"\n      ]\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:calculation:mm3",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:calculation:mm3",\n      "label": "中級・掛け算3｜2桁×2桁",\n      "category_id": "calculation",\n      "category_label": "そろばん・計算",\n      "difficulty_id": "mm3",\n      "difficulty_label": "mm3",\n      "difficulty_order": 3,\n      "progression_group_id": "soroban:calculation:mul",\n      "skill_ids": [\n        "soroban:mul"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "challenge"\n      ],\n      "question_count_default": 12,\n      "question_count_options": [\n        4,\n        12\n      ],\n      "estimated_duration_ms": 300000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "チャレンジモード",\n        "中級・掛け算3｜2桁×2桁"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:mul"\n      ],\n      "next_menu_ids": []\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:calculation:md1",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:calculation:md1",\n      "label": "中級・割り算1｜1〜81÷1桁",\n      "category_id": "calculation",\n      "category_label": "そろばん・計算",\n      "difficulty_id": "md1",\n      "difficulty_label": "md1",\n      "difficulty_order": 1,\n      "progression_group_id": "soroban:calculation:div",\n      "skill_ids": [\n        "soroban:div"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "challenge"\n      ],\n      "question_count_default": 12,\n      "question_count_options": [\n        4,\n        12\n      ],\n      "estimated_duration_ms": 300000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "チャレンジモード",\n        "中級・割り算1｜1〜81÷1桁"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:div"\n      ],\n      "next_menu_ids": [\n        "soroban:calculation:md2"\n      ]\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:calculation:md2",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:calculation:md2",\n      "label": "中級・割り算2｜3桁÷1桁",\n      "category_id": "calculation",\n      "category_label": "そろばん・計算",\n      "difficulty_id": "md2",\n      "difficulty_label": "md2",\n      "difficulty_order": 2,\n      "progression_group_id": "soroban:calculation:div",\n      "skill_ids": [\n        "soroban:div"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "challenge"\n      ],\n      "question_count_default": 12,\n      "question_count_options": [\n        4,\n        12\n      ],\n      "estimated_duration_ms": 300000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "チャレンジモード",\n        "中級・割り算2｜3桁÷1桁"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:div"\n      ],\n      "next_menu_ids": [\n        "soroban:calculation:md3"\n      ]\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:calculation:md3",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:calculation:md3",\n      "label": "中級・割り算3｜3桁÷2桁",\n      "category_id": "calculation",\n      "category_label": "そろばん・計算",\n      "difficulty_id": "md3",\n      "difficulty_label": "md3",\n      "difficulty_order": 3,\n      "progression_group_id": "soroban:calculation:div",\n      "skill_ids": [\n        "soroban:div"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "challenge"\n      ],\n      "question_count_default": 12,\n      "question_count_options": [\n        4,\n        12\n      ],\n      "estimated_duration_ms": 300000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "チャレンジモード",\n        "中級・割り算3｜3桁÷2桁"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:div"\n      ],\n      "next_menu_ids": []\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:calculation:a1",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:calculation:a1",\n      "label": "上級1｜4桁の足し算・引き算",\n      "category_id": "calculation",\n      "category_label": "そろばん・計算",\n      "difficulty_id": "a1",\n      "difficulty_label": "a1",\n      "difficulty_order": 1,\n      "progression_group_id": "soroban:calculation:advanced",\n      "skill_ids": [\n        "soroban:advanced"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "challenge"\n      ],\n      "question_count_default": 12,\n      "question_count_options": [\n        4,\n        12\n      ],\n      "estimated_duration_ms": 300000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "チャレンジモード",\n        "上級1｜4桁の足し算・引き算"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:add",\n        "soroban:sub"\n      ],\n      "next_menu_ids": [\n        "soroban:calculation:a2"\n      ]\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:calculation:a2",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:calculation:a2",\n      "label": "上級2｜3桁×2桁 / 4桁÷2桁",\n      "category_id": "calculation",\n      "category_label": "そろばん・計算",\n      "difficulty_id": "a2",\n      "difficulty_label": "a2",\n      "difficulty_order": 2,\n      "progression_group_id": "soroban:calculation:advanced",\n      "skill_ids": [\n        "soroban:advanced"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "challenge"\n      ],\n      "question_count_default": 12,\n      "question_count_options": [\n        4,\n        12\n      ],\n      "estimated_duration_ms": 300000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "チャレンジモード",\n        "上級2｜3桁×2桁 / 4桁÷2桁"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:mul",\n        "soroban:div"\n      ],\n      "next_menu_ids": [\n        "soroban:calculation:a3"\n      ]\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:calculation:a3",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:calculation:a3",\n      "label": "上級3｜3桁×3桁 / 5桁÷3桁",\n      "category_id": "calculation",\n      "category_label": "そろばん・計算",\n      "difficulty_id": "a3",\n      "difficulty_label": "a3",\n      "difficulty_order": 3,\n      "progression_group_id": "soroban:calculation:advanced",\n      "skill_ids": [\n        "soroban:advanced"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "challenge"\n      ],\n      "question_count_default": 12,\n      "question_count_options": [\n        4,\n        12\n      ],\n      "estimated_duration_ms": 300000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "チャレンジモード",\n        "上級3｜3桁×3桁 / 5桁÷3桁"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:mul",\n        "soroban:div"\n      ],\n      "next_menu_ids": []\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:hosu:add:1",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:hosu:add:1",\n      "label": "足し算・初級",\n      "category_id": "hosu",\n      "category_label": "補数名人",\n      "difficulty_id": "add:1",\n      "difficulty_label": "add:1",\n      "difficulty_order": 1,\n      "progression_group_id": "soroban:hosu:add",\n      "skill_ids": [\n        "soroban:complement:add"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "challenge"\n      ],\n      "question_count_default": 12,\n      "question_count_options": [\n        12\n      ],\n      "estimated_duration_ms": 480000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり40秒×12問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "補数名人",\n        "足し算・初級"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:complement:add",\n        "soroban:complement:5",\n        "soroban:complement:10"\n      ],\n      "next_menu_ids": [\n        "soroban:hosu:add:2"\n      ]\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:hosu:add:2",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:hosu:add:2",\n      "label": "足し算・中級",\n      "category_id": "hosu",\n      "category_label": "補数名人",\n      "difficulty_id": "add:2",\n      "difficulty_label": "add:2",\n      "difficulty_order": 2,\n      "progression_group_id": "soroban:hosu:add",\n      "skill_ids": [\n        "soroban:complement:add"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "challenge"\n      ],\n      "question_count_default": 12,\n      "question_count_options": [\n        12\n      ],\n      "estimated_duration_ms": 600000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり50秒×12問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "補数名人",\n        "足し算・中級"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:complement:add",\n        "soroban:complement:5",\n        "soroban:complement:10"\n      ],\n      "next_menu_ids": [\n        "soroban:hosu:add:3"\n      ]\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:hosu:add:3",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:hosu:add:3",\n      "label": "足し算・上級",\n      "category_id": "hosu",\n      "category_label": "補数名人",\n      "difficulty_id": "add:3",\n      "difficulty_label": "add:3",\n      "difficulty_order": 3,\n      "progression_group_id": "soroban:hosu:add",\n      "skill_ids": [\n        "soroban:complement:add"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "challenge"\n      ],\n      "question_count_default": 12,\n      "question_count_options": [\n        12\n      ],\n      "estimated_duration_ms": 720000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり60秒×12問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "補数名人",\n        "足し算・上級"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:complement:add",\n        "soroban:complement:5",\n        "soroban:complement:10"\n      ],\n      "next_menu_ids": []\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:hosu:sub:1",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:hosu:sub:1",\n      "label": "引き算・初級",\n      "category_id": "hosu",\n      "category_label": "補数名人",\n      "difficulty_id": "sub:1",\n      "difficulty_label": "sub:1",\n      "difficulty_order": 1,\n      "progression_group_id": "soroban:hosu:sub",\n      "skill_ids": [\n        "soroban:complement:sub"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "challenge"\n      ],\n      "question_count_default": 12,\n      "question_count_options": [\n        12\n      ],\n      "estimated_duration_ms": 480000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり40秒×12問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "補数名人",\n        "引き算・初級"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:complement:sub",\n        "soroban:complement:5",\n        "soroban:complement:10"\n      ],\n      "next_menu_ids": [\n        "soroban:hosu:sub:2"\n      ]\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:hosu:sub:2",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:hosu:sub:2",\n      "label": "引き算・中級",\n      "category_id": "hosu",\n      "category_label": "補数名人",\n      "difficulty_id": "sub:2",\n      "difficulty_label": "sub:2",\n      "difficulty_order": 2,\n      "progression_group_id": "soroban:hosu:sub",\n      "skill_ids": [\n        "soroban:complement:sub"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "challenge"\n      ],\n      "question_count_default": 12,\n      "question_count_options": [\n        12\n      ],\n      "estimated_duration_ms": 600000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり50秒×12問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "補数名人",\n        "引き算・中級"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:complement:sub",\n        "soroban:complement:5",\n        "soroban:complement:10"\n      ],\n      "next_menu_ids": [\n        "soroban:hosu:sub:3"\n      ]\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:hosu:sub:3",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:hosu:sub:3",\n      "label": "引き算・上級",\n      "category_id": "hosu",\n      "category_label": "補数名人",\n      "difficulty_id": "sub:3",\n      "difficulty_label": "sub:3",\n      "difficulty_order": 3,\n      "progression_group_id": "soroban:hosu:sub",\n      "skill_ids": [\n        "soroban:complement:sub"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "challenge"\n      ],\n      "question_count_default": 12,\n      "question_count_options": [\n        12\n      ],\n      "estimated_duration_ms": 720000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり60秒×12問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "補数名人",\n        "引き算・上級"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:complement:sub",\n        "soroban:complement:5",\n        "soroban:complement:10"\n      ],\n      "next_menu_ids": []\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:kuku:1",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:kuku:1",\n      "label": "初級",\n      "category_id": "kuku",\n      "category_label": "九九名人",\n      "difficulty_id": "1",\n      "difficulty_label": "1",\n      "difficulty_order": 1,\n      "progression_group_id": "soroban:kuku",\n      "skill_ids": [\n        "soroban:multiplication"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "challenge"\n      ],\n      "question_count_default": 10,\n      "question_count_options": [\n        10\n      ],\n      "estimated_duration_ms": 50000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり5秒×10問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "九九名人",\n        "初級"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:multiplication",\n        "soroban:kuku:1",\n        "soroban:kuku:2",\n        "soroban:kuku:3",\n        "soroban:kuku:4",\n        "soroban:kuku:5",\n        "soroban:kuku:6",\n        "soroban:kuku:7",\n        "soroban:kuku:8",\n        "soroban:kuku:9"\n      ],\n      "next_menu_ids": [\n        "soroban:kuku:2"\n      ]\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:kuku:2",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:kuku:2",\n      "label": "中級",\n      "category_id": "kuku",\n      "category_label": "九九名人",\n      "difficulty_id": "2",\n      "difficulty_label": "2",\n      "difficulty_order": 2,\n      "progression_group_id": "soroban:kuku",\n      "skill_ids": [\n        "soroban:multiplication"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "challenge"\n      ],\n      "question_count_default": 10,\n      "question_count_options": [\n        10\n      ],\n      "estimated_duration_ms": 50000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり5秒×10問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "九九名人",\n        "中級"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:multiplication",\n        "soroban:kuku:1",\n        "soroban:kuku:2",\n        "soroban:kuku:3",\n        "soroban:kuku:4",\n        "soroban:kuku:5",\n        "soroban:kuku:6",\n        "soroban:kuku:7",\n        "soroban:kuku:8",\n        "soroban:kuku:9"\n      ],\n      "next_menu_ids": [\n        "soroban:kuku:3"\n      ]\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:kuku:3",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:kuku:3",\n      "label": "上級・完全ランダム10問",\n      "category_id": "kuku",\n      "category_label": "九九名人",\n      "difficulty_id": "3",\n      "difficulty_label": "3",\n      "difficulty_order": 3,\n      "progression_group_id": "soroban:kuku",\n      "skill_ids": [\n        "soroban:multiplication"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "challenge"\n      ],\n      "question_count_default": 10,\n      "question_count_options": [\n        10\n      ],\n      "estimated_duration_ms": 50000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり5秒×10問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "九九名人",\n        "上級・完全ランダム10問"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:multiplication",\n        "soroban:kuku:1",\n        "soroban:kuku:2",\n        "soroban:kuku:3",\n        "soroban:kuku:4",\n        "soroban:kuku:5",\n        "soroban:kuku:6",\n        "soroban:kuku:7",\n        "soroban:kuku:8",\n        "soroban:kuku:9"\n      ],\n      "next_menu_ids": [\n        "soroban:kuku:4"\n      ]\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:kuku:4",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:kuku:4",\n      "label": "特級・完全ランダム30問",\n      "category_id": "kuku",\n      "category_label": "九九名人",\n      "difficulty_id": "4",\n      "difficulty_label": "4",\n      "difficulty_order": 4,\n      "progression_group_id": "soroban:kuku",\n      "skill_ids": [\n        "soroban:multiplication"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "challenge"\n      ],\n      "question_count_default": 30,\n      "question_count_options": [\n        30\n      ],\n      "estimated_duration_ms": 150000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり5秒×30問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "九九名人",\n        "特級・完全ランダム30問"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:multiplication",\n        "soroban:kuku:1",\n        "soroban:kuku:2",\n        "soroban:kuku:3",\n        "soroban:kuku:4",\n        "soroban:kuku:5",\n        "soroban:kuku:6",\n        "soroban:kuku:7",\n        "soroban:kuku:8",\n        "soroban:kuku:9"\n      ],\n      "next_menu_ids": [\n        "soroban:kuku:5"\n      ]\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:kuku:5",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:kuku:5",\n      "label": "名人",\n      "category_id": "kuku",\n      "category_label": "九九名人",\n      "difficulty_id": "5",\n      "difficulty_label": "5",\n      "difficulty_order": 5,\n      "progression_group_id": "soroban:kuku",\n      "skill_ids": [\n        "soroban:multiplication"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "challenge"\n      ],\n      "question_count_default": 90,\n      "question_count_options": [\n        90\n      ],\n      "estimated_duration_ms": 450000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり5秒×90問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "九九名人",\n        "名人"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:multiplication",\n        "soroban:kuku:1",\n        "soroban:kuku:2",\n        "soroban:kuku:3",\n        "soroban:kuku:4",\n        "soroban:kuku:5",\n        "soroban:kuku:6",\n        "soroban:kuku:7",\n        "soroban:kuku:8",\n        "soroban:kuku:9"\n      ],\n      "next_menu_ids": []\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:anzan:1",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:anzan:1",\n      "label": "初級",\n      "category_id": "anzan",\n      "category_label": "暗算名人",\n      "difficulty_id": "1",\n      "difficulty_label": "1",\n      "difficulty_order": 1,\n      "progression_group_id": "soroban:anzan",\n      "skill_ids": [\n        "soroban:mental_arithmetic"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "challenge"\n      ],\n      "question_count_default": 10,\n      "question_count_options": [\n        10\n      ],\n      "estimated_duration_ms": 150000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり15秒×10問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "暗算名人",\n        "初級"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:mental_arithmetic",\n        "soroban:mental_addition"\n      ],\n      "next_menu_ids": [\n        "soroban:anzan:2"\n      ]\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:anzan:2",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:anzan:2",\n      "label": "中級",\n      "category_id": "anzan",\n      "category_label": "暗算名人",\n      "difficulty_id": "2",\n      "difficulty_label": "2",\n      "difficulty_order": 2,\n      "progression_group_id": "soroban:anzan",\n      "skill_ids": [\n        "soroban:mental_arithmetic"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "challenge"\n      ],\n      "question_count_default": 10,\n      "question_count_options": [\n        10\n      ],\n      "estimated_duration_ms": 200000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり20秒×10問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "暗算名人",\n        "中級"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:mental_arithmetic",\n        "soroban:mental_addition",\n        "soroban:mental_subtraction"\n      ],\n      "next_menu_ids": [\n        "soroban:anzan:3"\n      ]\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:anzan:3",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:anzan:3",\n      "label": "上級",\n      "category_id": "anzan",\n      "category_label": "暗算名人",\n      "difficulty_id": "3",\n      "difficulty_label": "3",\n      "difficulty_order": 3,\n      "progression_group_id": "soroban:anzan",\n      "skill_ids": [\n        "soroban:mental_arithmetic"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "challenge"\n      ],\n      "question_count_default": 10,\n      "question_count_options": [\n        10\n      ],\n      "estimated_duration_ms": 250000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり25秒×10問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "暗算名人",\n        "上級"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:mental_arithmetic",\n        "soroban:mental_addition",\n        "soroban:mental_subtraction"\n      ],\n      "next_menu_ids": []\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:tutorial:add1",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:tutorial:add1",\n      "label": "1〜4をそのまま足す",\n      "category_id": "calculation",\n      "category_label": "そろばん・計算",\n      "difficulty_id": "add1",\n      "difficulty_label": "add1",\n      "difficulty_order": 1,\n      "progression_group_id": "soroban:tutorial:add",\n      "skill_ids": [\n        "soroban:lesson:add1"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "learn"\n      ],\n      "question_count_default": 1,\n      "question_count_options": [\n        1\n      ],\n      "estimated_duration_ms": 90000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり90秒×1問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "珠の動きで学ぶ",\n        "足し算",\n        "1〜4をそのまま足す"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:lesson:add1"\n      ],\n      "next_menu_ids": [\n        "soroban:tutorial:add2"\n      ]\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:tutorial:add2",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:tutorial:add2",\n      "label": "5珠と1珠を組み合わせる",\n      "category_id": "calculation",\n      "category_label": "そろばん・計算",\n      "difficulty_id": "add2",\n      "difficulty_label": "add2",\n      "difficulty_order": 2,\n      "progression_group_id": "soroban:tutorial:add",\n      "skill_ids": [\n        "soroban:lesson:add2"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "learn"\n      ],\n      "question_count_default": 1,\n      "question_count_options": [\n        1\n      ],\n      "estimated_duration_ms": 90000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり90秒×1問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "珠の動きで学ぶ",\n        "足し算",\n        "5珠と1珠を組み合わせる"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:lesson:add2"\n      ],\n      "next_menu_ids": [\n        "soroban:tutorial:add3"\n      ]\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:tutorial:add3",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:tutorial:add3",\n      "label": "5の補数で足す",\n      "category_id": "calculation",\n      "category_label": "そろばん・計算",\n      "difficulty_id": "add3",\n      "difficulty_label": "add3",\n      "difficulty_order": 3,\n      "progression_group_id": "soroban:tutorial:add",\n      "skill_ids": [\n        "soroban:lesson:add3"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "learn"\n      ],\n      "question_count_default": 1,\n      "question_count_options": [\n        1\n      ],\n      "estimated_duration_ms": 90000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり90秒×1問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "珠の動きで学ぶ",\n        "足し算",\n        "5の補数で足す"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:lesson:add3"\n      ],\n      "next_menu_ids": [\n        "soroban:tutorial:add4"\n      ]\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:tutorial:add4",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:tutorial:add4",\n      "label": "10の補数で繰り上がる",\n      "category_id": "calculation",\n      "category_label": "そろばん・計算",\n      "difficulty_id": "add4",\n      "difficulty_label": "add4",\n      "difficulty_order": 4,\n      "progression_group_id": "soroban:tutorial:add",\n      "skill_ids": [\n        "soroban:lesson:add4"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "learn"\n      ],\n      "question_count_default": 1,\n      "question_count_options": [\n        1\n      ],\n      "estimated_duration_ms": 90000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり90秒×1問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "珠の動きで学ぶ",\n        "足し算",\n        "10の補数で繰り上がる"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:lesson:add4"\n      ],\n      "next_menu_ids": [\n        "soroban:tutorial:add5"\n      ]\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:tutorial:add5",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:tutorial:add5",\n      "label": "2桁の繰り上がり",\n      "category_id": "calculation",\n      "category_label": "そろばん・計算",\n      "difficulty_id": "add5",\n      "difficulty_label": "add5",\n      "difficulty_order": 5,\n      "progression_group_id": "soroban:tutorial:add",\n      "skill_ids": [\n        "soroban:lesson:add5"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "learn"\n      ],\n      "question_count_default": 1,\n      "question_count_options": [\n        1\n      ],\n      "estimated_duration_ms": 90000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり90秒×1問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "珠の動きで学ぶ",\n        "足し算",\n        "2桁の繰り上がり"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:lesson:add5"\n      ],\n      "next_menu_ids": []\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:tutorial:sub1",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:tutorial:sub1",\n      "label": "そのまま引く",\n      "category_id": "calculation",\n      "category_label": "そろばん・計算",\n      "difficulty_id": "sub1",\n      "difficulty_label": "sub1",\n      "difficulty_order": 1,\n      "progression_group_id": "soroban:tutorial:sub",\n      "skill_ids": [\n        "soroban:lesson:sub1"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "learn"\n      ],\n      "question_count_default": 1,\n      "question_count_options": [\n        1\n      ],\n      "estimated_duration_ms": 90000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり90秒×1問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "珠の動きで学ぶ",\n        "引き算",\n        "そのまま引く"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:lesson:sub1"\n      ],\n      "next_menu_ids": [\n        "soroban:tutorial:sub2"\n      ]\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:tutorial:sub2",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:tutorial:sub2",\n      "label": "5珠から直接引く",\n      "category_id": "calculation",\n      "category_label": "そろばん・計算",\n      "difficulty_id": "sub2",\n      "difficulty_label": "sub2",\n      "difficulty_order": 2,\n      "progression_group_id": "soroban:tutorial:sub",\n      "skill_ids": [\n        "soroban:lesson:sub2"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "learn"\n      ],\n      "question_count_default": 1,\n      "question_count_options": [\n        1\n      ],\n      "estimated_duration_ms": 90000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり90秒×1問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "珠の動きで学ぶ",\n        "引き算",\n        "5珠から直接引く"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:lesson:sub2"\n      ],\n      "next_menu_ids": [\n        "soroban:tutorial:sub3"\n      ]\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:tutorial:sub3",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:tutorial:sub3",\n      "label": "5の補数で引く",\n      "category_id": "calculation",\n      "category_label": "そろばん・計算",\n      "difficulty_id": "sub3",\n      "difficulty_label": "sub3",\n      "difficulty_order": 3,\n      "progression_group_id": "soroban:tutorial:sub",\n      "skill_ids": [\n        "soroban:lesson:sub3"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "learn"\n      ],\n      "question_count_default": 1,\n      "question_count_options": [\n        1\n      ],\n      "estimated_duration_ms": 90000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり90秒×1問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "珠の動きで学ぶ",\n        "引き算",\n        "5の補数で引く"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:lesson:sub3"\n      ],\n      "next_menu_ids": [\n        "soroban:tutorial:sub4"\n      ]\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:tutorial:sub4",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:tutorial:sub4",\n      "label": "10の補数で繰り下がる",\n      "category_id": "calculation",\n      "category_label": "そろばん・計算",\n      "difficulty_id": "sub4",\n      "difficulty_label": "sub4",\n      "difficulty_order": 4,\n      "progression_group_id": "soroban:tutorial:sub",\n      "skill_ids": [\n        "soroban:lesson:sub4"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "learn"\n      ],\n      "question_count_default": 1,\n      "question_count_options": [\n        1\n      ],\n      "estimated_duration_ms": 90000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり90秒×1問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "珠の動きで学ぶ",\n        "引き算",\n        "10の補数で繰り下がる"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:lesson:sub4"\n      ],\n      "next_menu_ids": [\n        "soroban:tutorial:sub5"\n      ]\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:tutorial:sub5",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:tutorial:sub5",\n      "label": "2桁の繰り下がり",\n      "category_id": "calculation",\n      "category_label": "そろばん・計算",\n      "difficulty_id": "sub5",\n      "difficulty_label": "sub5",\n      "difficulty_order": 5,\n      "progression_group_id": "soroban:tutorial:sub",\n      "skill_ids": [\n        "soroban:lesson:sub5"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "learn"\n      ],\n      "question_count_default": 1,\n      "question_count_options": [\n        1\n      ],\n      "estimated_duration_ms": 90000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり90秒×1問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "珠の動きで学ぶ",\n        "引き算",\n        "2桁の繰り下がり"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:lesson:sub5"\n      ],\n      "next_menu_ids": []\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:tutorial:mul1",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:tutorial:mul1",\n      "label": "九九の答えを珠に置く",\n      "category_id": "calculation",\n      "category_label": "そろばん・計算",\n      "difficulty_id": "mul1",\n      "difficulty_label": "mul1",\n      "difficulty_order": 1,\n      "progression_group_id": "soroban:tutorial:mul",\n      "skill_ids": [\n        "soroban:lesson:mul1"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "learn"\n      ],\n      "question_count_default": 1,\n      "question_count_options": [\n        1\n      ],\n      "estimated_duration_ms": 90000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり90秒×1問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "珠の動きで学ぶ",\n        "掛け算",\n        "九九の答えを珠に置く"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:lesson:mul1"\n      ],\n      "next_menu_ids": [\n        "soroban:tutorial:mul2"\n      ]\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:tutorial:mul2",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:tutorial:mul2",\n      "label": "2桁×1桁の部分積",\n      "category_id": "calculation",\n      "category_label": "そろばん・計算",\n      "difficulty_id": "mul2",\n      "difficulty_label": "mul2",\n      "difficulty_order": 2,\n      "progression_group_id": "soroban:tutorial:mul",\n      "skill_ids": [\n        "soroban:lesson:mul2"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "learn"\n      ],\n      "question_count_default": 1,\n      "question_count_options": [\n        1\n      ],\n      "estimated_duration_ms": 90000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり90秒×1問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "珠の動きで学ぶ",\n        "掛け算",\n        "2桁×1桁の部分積"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:lesson:mul2"\n      ],\n      "next_menu_ids": [\n        "soroban:tutorial:mul3"\n      ]\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:tutorial:mul3",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:tutorial:mul3",\n      "label": "2桁×2桁",\n      "category_id": "calculation",\n      "category_label": "そろばん・計算",\n      "difficulty_id": "mul3",\n      "difficulty_label": "mul3",\n      "difficulty_order": 3,\n      "progression_group_id": "soroban:tutorial:mul",\n      "skill_ids": [\n        "soroban:lesson:mul3"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "learn"\n      ],\n      "question_count_default": 1,\n      "question_count_options": [\n        1\n      ],\n      "estimated_duration_ms": 90000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり90秒×1問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "珠の動きで学ぶ",\n        "掛け算",\n        "2桁×2桁"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:lesson:mul3"\n      ],\n      "next_menu_ids": [\n        "soroban:tutorial:mul4"\n      ]\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:tutorial:mul4",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:tutorial:mul4",\n      "label": "0がある数の位取り",\n      "category_id": "calculation",\n      "category_label": "そろばん・計算",\n      "difficulty_id": "mul4",\n      "difficulty_label": "mul4",\n      "difficulty_order": 4,\n      "progression_group_id": "soroban:tutorial:mul",\n      "skill_ids": [\n        "soroban:lesson:mul4"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "learn"\n      ],\n      "question_count_default": 1,\n      "question_count_options": [\n        1\n      ],\n      "estimated_duration_ms": 90000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり90秒×1問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "珠の動きで学ぶ",\n        "掛け算",\n        "0がある数の位取り"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:lesson:mul4"\n      ],\n      "next_menu_ids": []\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:tutorial:div1",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:tutorial:div1",\n      "label": "1桁÷1桁",\n      "category_id": "calculation",\n      "category_label": "そろばん・計算",\n      "difficulty_id": "div1",\n      "difficulty_label": "div1",\n      "difficulty_order": 1,\n      "progression_group_id": "soroban:tutorial:div",\n      "skill_ids": [\n        "soroban:lesson:div1"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "learn"\n      ],\n      "question_count_default": 1,\n      "question_count_options": [\n        1\n      ],\n      "estimated_duration_ms": 90000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり90秒×1問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "珠の動きで学ぶ",\n        "割り算",\n        "1桁÷1桁"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:lesson:div1"\n      ],\n      "next_menu_ids": [\n        "soroban:tutorial:div2"\n      ]\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:tutorial:div2",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:tutorial:div2",\n      "label": "2桁÷1桁",\n      "category_id": "calculation",\n      "category_label": "そろばん・計算",\n      "difficulty_id": "div2",\n      "difficulty_label": "div2",\n      "difficulty_order": 2,\n      "progression_group_id": "soroban:tutorial:div",\n      "skill_ids": [\n        "soroban:lesson:div2"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "learn"\n      ],\n      "question_count_default": 1,\n      "question_count_options": [\n        1\n      ],\n      "estimated_duration_ms": 90000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり90秒×1問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "珠の動きで学ぶ",\n        "割り算",\n        "2桁÷1桁"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:lesson:div2"\n      ],\n      "next_menu_ids": [\n        "soroban:tutorial:div3"\n      ]\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:tutorial:div3",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:tutorial:div3",\n      "label": "3桁÷1桁",\n      "category_id": "calculation",\n      "category_label": "そろばん・計算",\n      "difficulty_id": "div3",\n      "difficulty_label": "div3",\n      "difficulty_order": 3,\n      "progression_group_id": "soroban:tutorial:div",\n      "skill_ids": [\n        "soroban:lesson:div3"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "learn"\n      ],\n      "question_count_default": 1,\n      "question_count_options": [\n        1\n      ],\n      "estimated_duration_ms": 90000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり90秒×1問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "珠の動きで学ぶ",\n        "割り算",\n        "3桁÷1桁"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:lesson:div3"\n      ],\n      "next_menu_ids": [\n        "soroban:tutorial:div4"\n      ]\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:tutorial:div4",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:tutorial:div4",\n      "label": "2桁で割る",\n      "category_id": "calculation",\n      "category_label": "そろばん・計算",\n      "difficulty_id": "div4",\n      "difficulty_label": "div4",\n      "difficulty_order": 4,\n      "progression_group_id": "soroban:tutorial:div",\n      "skill_ids": [\n        "soroban:lesson:div4"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "learn"\n      ],\n      "question_count_default": 1,\n      "question_count_options": [\n        1\n      ],\n      "estimated_duration_ms": 90000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり90秒×1問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "珠の動きで学ぶ",\n        "割り算",\n        "2桁で割る"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:lesson:div4"\n      ],\n      "next_menu_ids": []\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:kuku:read:1",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:kuku:read:1",\n      "label": "1の段・読み上げ",\n      "category_id": "kuku",\n      "category_label": "九九名人",\n      "difficulty_id": "read",\n      "difficulty_label": "read",\n      "difficulty_order": 1,\n      "progression_group_id": "soroban:kuku:reading",\n      "skill_ids": [\n        "soroban:kuku:1"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "reading_aloud"\n      ],\n      "question_count_default": 1,\n      "question_count_options": [\n        1\n      ],\n      "estimated_duration_ms": 30000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり30秒×1問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "九九名人",\n        "九九一覧表",\n        "1の段の読み上げ"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:multiplication",\n        "soroban:kuku:1"\n      ],\n      "next_menu_ids": []\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:kuku:read:2",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:kuku:read:2",\n      "label": "2の段・読み上げ",\n      "category_id": "kuku",\n      "category_label": "九九名人",\n      "difficulty_id": "read",\n      "difficulty_label": "read",\n      "difficulty_order": 2,\n      "progression_group_id": "soroban:kuku:reading",\n      "skill_ids": [\n        "soroban:kuku:2"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "reading_aloud"\n      ],\n      "question_count_default": 1,\n      "question_count_options": [\n        1\n      ],\n      "estimated_duration_ms": 30000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり30秒×1問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "九九名人",\n        "九九一覧表",\n        "2の段の読み上げ"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:multiplication",\n        "soroban:kuku:2"\n      ],\n      "next_menu_ids": []\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:kuku:read:3",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:kuku:read:3",\n      "label": "3の段・読み上げ",\n      "category_id": "kuku",\n      "category_label": "九九名人",\n      "difficulty_id": "read",\n      "difficulty_label": "read",\n      "difficulty_order": 3,\n      "progression_group_id": "soroban:kuku:reading",\n      "skill_ids": [\n        "soroban:kuku:3"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "reading_aloud"\n      ],\n      "question_count_default": 1,\n      "question_count_options": [\n        1\n      ],\n      "estimated_duration_ms": 30000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり30秒×1問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "九九名人",\n        "九九一覧表",\n        "3の段の読み上げ"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:multiplication",\n        "soroban:kuku:3"\n      ],\n      "next_menu_ids": []\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:kuku:read:4",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:kuku:read:4",\n      "label": "4の段・読み上げ",\n      "category_id": "kuku",\n      "category_label": "九九名人",\n      "difficulty_id": "read",\n      "difficulty_label": "read",\n      "difficulty_order": 4,\n      "progression_group_id": "soroban:kuku:reading",\n      "skill_ids": [\n        "soroban:kuku:4"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "reading_aloud"\n      ],\n      "question_count_default": 1,\n      "question_count_options": [\n        1\n      ],\n      "estimated_duration_ms": 30000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり30秒×1問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "九九名人",\n        "九九一覧表",\n        "4の段の読み上げ"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:multiplication",\n        "soroban:kuku:4"\n      ],\n      "next_menu_ids": []\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:kuku:read:5",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:kuku:read:5",\n      "label": "5の段・読み上げ",\n      "category_id": "kuku",\n      "category_label": "九九名人",\n      "difficulty_id": "read",\n      "difficulty_label": "read",\n      "difficulty_order": 5,\n      "progression_group_id": "soroban:kuku:reading",\n      "skill_ids": [\n        "soroban:kuku:5"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "reading_aloud"\n      ],\n      "question_count_default": 1,\n      "question_count_options": [\n        1\n      ],\n      "estimated_duration_ms": 30000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり30秒×1問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "九九名人",\n        "九九一覧表",\n        "5の段の読み上げ"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:multiplication",\n        "soroban:kuku:5"\n      ],\n      "next_menu_ids": []\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:kuku:read:6",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:kuku:read:6",\n      "label": "6の段・読み上げ",\n      "category_id": "kuku",\n      "category_label": "九九名人",\n      "difficulty_id": "read",\n      "difficulty_label": "read",\n      "difficulty_order": 6,\n      "progression_group_id": "soroban:kuku:reading",\n      "skill_ids": [\n        "soroban:kuku:6"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "reading_aloud"\n      ],\n      "question_count_default": 1,\n      "question_count_options": [\n        1\n      ],\n      "estimated_duration_ms": 30000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり30秒×1問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "九九名人",\n        "九九一覧表",\n        "6の段の読み上げ"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:multiplication",\n        "soroban:kuku:6"\n      ],\n      "next_menu_ids": []\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:kuku:read:7",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:kuku:read:7",\n      "label": "7の段・読み上げ",\n      "category_id": "kuku",\n      "category_label": "九九名人",\n      "difficulty_id": "read",\n      "difficulty_label": "read",\n      "difficulty_order": 7,\n      "progression_group_id": "soroban:kuku:reading",\n      "skill_ids": [\n        "soroban:kuku:7"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "reading_aloud"\n      ],\n      "question_count_default": 1,\n      "question_count_options": [\n        1\n      ],\n      "estimated_duration_ms": 30000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり30秒×1問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "九九名人",\n        "九九一覧表",\n        "7の段の読み上げ"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:multiplication",\n        "soroban:kuku:7"\n      ],\n      "next_menu_ids": []\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:kuku:read:8",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:kuku:read:8",\n      "label": "8の段・読み上げ",\n      "category_id": "kuku",\n      "category_label": "九九名人",\n      "difficulty_id": "read",\n      "difficulty_label": "read",\n      "difficulty_order": 8,\n      "progression_group_id": "soroban:kuku:reading",\n      "skill_ids": [\n        "soroban:kuku:8"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "reading_aloud"\n      ],\n      "question_count_default": 1,\n      "question_count_options": [\n        1\n      ],\n      "estimated_duration_ms": 30000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり30秒×1問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "九九名人",\n        "九九一覧表",\n        "8の段の読み上げ"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:multiplication",\n        "soroban:kuku:8"\n      ],\n      "next_menu_ids": []\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "menu",\n    "entry_id": "soroban:kuku:read:9",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "menu_id": "soroban:kuku:read:9",\n      "label": "9の段・読み上げ",\n      "category_id": "kuku",\n      "category_label": "九九名人",\n      "difficulty_id": "read",\n      "difficulty_label": "read",\n      "difficulty_order": 9,\n      "progression_group_id": "soroban:kuku:reading",\n      "skill_ids": [\n        "soroban:kuku:9"\n      ],\n      "prerequisite_skill_ids": null,\n      "mode_options": [\n        "reading_aloud"\n      ],\n      "question_count_default": 1,\n      "question_count_options": [\n        1\n      ],\n      "estimated_duration_ms": 30000,\n      "duration_basis": "provisional",\n      "duration_sample_count": 0,\n      "duration_estimate_note": "仮設定：1問あたり30秒×1問。実測による裏付けは未取得。",\n      "age_min": null,\n      "age_max": null,\n      "age_basis": null,\n      "launch_url": "",\n      "supports_direct_launch": false,\n      "selection_instructions": [\n        "九九名人",\n        "九九一覧表",\n        "9の段の読み上げ"\n      ],\n      "is_active": true,\n      "available_skill_ids": [\n        "soroban:multiplication",\n        "soroban:kuku:9"\n      ],\n      "next_menu_ids": []\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "skill",\n    "entry_id": "soroban:add",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "skill_id": "soroban:add",\n      "label": "soroban:add",\n      "parent_skill_id": null,\n      "category_id": "calculation",\n      "definition": "既存の出題経路と問題定義に対応する技能。実際の珠操作を観測したという意味ではない。",\n      "observation_rule": "自動採点された回答・小段階の回答と支援イベントを別々に参照する。複合問題の誤答を全技能の誤りと断定しない。",\n      "prerequisite_skill_ids": null,\n      "progression_group_id": "soroban:calculation:add",\n      "difficulty_axes": [\n        "difficulty_id"\n      ],\n      "is_active": true\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "skill",\n    "entry_id": "soroban:sub",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "skill_id": "soroban:sub",\n      "label": "soroban:sub",\n      "parent_skill_id": null,\n      "category_id": "calculation",\n      "definition": "既存の出題経路と問題定義に対応する技能。実際の珠操作を観測したという意味ではない。",\n      "observation_rule": "自動採点された回答・小段階の回答と支援イベントを別々に参照する。複合問題の誤答を全技能の誤りと断定しない。",\n      "prerequisite_skill_ids": null,\n      "progression_group_id": "soroban:calculation:sub",\n      "difficulty_axes": [\n        "difficulty_id"\n      ],\n      "is_active": true\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "skill",\n    "entry_id": "soroban:mul",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "skill_id": "soroban:mul",\n      "label": "soroban:mul",\n      "parent_skill_id": null,\n      "category_id": "calculation",\n      "definition": "既存の出題経路と問題定義に対応する技能。実際の珠操作を観測したという意味ではない。",\n      "observation_rule": "自動採点された回答・小段階の回答と支援イベントを別々に参照する。複合問題の誤答を全技能の誤りと断定しない。",\n      "prerequisite_skill_ids": null,\n      "progression_group_id": "soroban:calculation:mul",\n      "difficulty_axes": [\n        "difficulty_id"\n      ],\n      "is_active": true\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "skill",\n    "entry_id": "soroban:div",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "skill_id": "soroban:div",\n      "label": "soroban:div",\n      "parent_skill_id": null,\n      "category_id": "calculation",\n      "definition": "既存の出題経路と問題定義に対応する技能。実際の珠操作を観測したという意味ではない。",\n      "observation_rule": "自動採点された回答・小段階の回答と支援イベントを別々に参照する。複合問題の誤答を全技能の誤りと断定しない。",\n      "prerequisite_skill_ids": null,\n      "progression_group_id": "soroban:calculation:div",\n      "difficulty_axes": [\n        "difficulty_id"\n      ],\n      "is_active": true\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "skill",\n    "entry_id": "soroban:advanced",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "skill_id": "soroban:advanced",\n      "label": "soroban:advanced",\n      "parent_skill_id": null,\n      "category_id": "calculation",\n      "definition": "既存の出題経路と問題定義に対応する技能。実際の珠操作を観測したという意味ではない。",\n      "observation_rule": "自動採点された回答・小段階の回答と支援イベントを別々に参照する。複合問題の誤答を全技能の誤りと断定しない。",\n      "prerequisite_skill_ids": null,\n      "progression_group_id": "soroban:calculation:advanced",\n      "difficulty_axes": [\n        "difficulty_id"\n      ],\n      "is_active": true\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "skill",\n    "entry_id": "soroban:complement:add",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "skill_id": "soroban:complement:add",\n      "label": "soroban:complement:add",\n      "parent_skill_id": null,\n      "category_id": "hosu",\n      "definition": "既存の出題経路と問題定義に対応する技能。実際の珠操作を観測したという意味ではない。",\n      "observation_rule": "自動採点された回答・小段階の回答と支援イベントを別々に参照する。複合問題の誤答を全技能の誤りと断定しない。",\n      "prerequisite_skill_ids": null,\n      "progression_group_id": "soroban:hosu:add",\n      "difficulty_axes": [\n        "difficulty_id"\n      ],\n      "is_active": true\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "skill",\n    "entry_id": "soroban:complement:sub",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "skill_id": "soroban:complement:sub",\n      "label": "soroban:complement:sub",\n      "parent_skill_id": null,\n      "category_id": "hosu",\n      "definition": "既存の出題経路と問題定義に対応する技能。実際の珠操作を観測したという意味ではない。",\n      "observation_rule": "自動採点された回答・小段階の回答と支援イベントを別々に参照する。複合問題の誤答を全技能の誤りと断定しない。",\n      "prerequisite_skill_ids": null,\n      "progression_group_id": "soroban:hosu:sub",\n      "difficulty_axes": [\n        "difficulty_id"\n      ],\n      "is_active": true\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "skill",\n    "entry_id": "soroban:multiplication",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "skill_id": "soroban:multiplication",\n      "label": "soroban:multiplication",\n      "parent_skill_id": null,\n      "category_id": "kuku",\n      "definition": "既存の出題経路と問題定義に対応する技能。実際の珠操作を観測したという意味ではない。",\n      "observation_rule": "自動採点された回答・小段階の回答と支援イベントを別々に参照する。複合問題の誤答を全技能の誤りと断定しない。",\n      "prerequisite_skill_ids": null,\n      "progression_group_id": "soroban:kuku",\n      "difficulty_axes": [\n        "difficulty_id"\n      ],\n      "is_active": true\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "skill",\n    "entry_id": "soroban:mental_arithmetic",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "skill_id": "soroban:mental_arithmetic",\n      "label": "soroban:mental_arithmetic",\n      "parent_skill_id": null,\n      "category_id": "anzan",\n      "definition": "既存の出題経路と問題定義に対応する技能。実際の珠操作を観測したという意味ではない。",\n      "observation_rule": "自動採点された回答・小段階の回答と支援イベントを別々に参照する。複合問題の誤答を全技能の誤りと断定しない。",\n      "prerequisite_skill_ids": null,\n      "progression_group_id": "soroban:anzan",\n      "difficulty_axes": [\n        "difficulty_id"\n      ],\n      "is_active": true\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "skill",\n    "entry_id": "soroban:lesson:add1",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "skill_id": "soroban:lesson:add1",\n      "label": "1〜4をそのまま足す",\n      "parent_skill_id": null,\n      "category_id": "calculation",\n      "definition": "既存の出題経路と問題定義に対応する技能。実際の珠操作を観測したという意味ではない。",\n      "observation_rule": "自動採点された回答・小段階の回答と支援イベントを別々に参照する。複合問題の誤答を全技能の誤りと断定しない。",\n      "prerequisite_skill_ids": null,\n      "progression_group_id": "soroban:tutorial:add",\n      "difficulty_axes": [\n        "difficulty_id"\n      ],\n      "is_active": true\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "skill",\n    "entry_id": "soroban:lesson:add2",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "skill_id": "soroban:lesson:add2",\n      "label": "5珠と1珠を組み合わせる",\n      "parent_skill_id": null,\n      "category_id": "calculation",\n      "definition": "既存の出題経路と問題定義に対応する技能。実際の珠操作を観測したという意味ではない。",\n      "observation_rule": "自動採点された回答・小段階の回答と支援イベントを別々に参照する。複合問題の誤答を全技能の誤りと断定しない。",\n      "prerequisite_skill_ids": null,\n      "progression_group_id": "soroban:tutorial:add",\n      "difficulty_axes": [\n        "difficulty_id"\n      ],\n      "is_active": true\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "skill",\n    "entry_id": "soroban:lesson:add3",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "skill_id": "soroban:lesson:add3",\n      "label": "5の補数で足す",\n      "parent_skill_id": null,\n      "category_id": "calculation",\n      "definition": "既存の出題経路と問題定義に対応する技能。実際の珠操作を観測したという意味ではない。",\n      "observation_rule": "自動採点された回答・小段階の回答と支援イベントを別々に参照する。複合問題の誤答を全技能の誤りと断定しない。",\n      "prerequisite_skill_ids": null,\n      "progression_group_id": "soroban:tutorial:add",\n      "difficulty_axes": [\n        "difficulty_id"\n      ],\n      "is_active": true\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "skill",\n    "entry_id": "soroban:lesson:add4",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "skill_id": "soroban:lesson:add4",\n      "label": "10の補数で繰り上がる",\n      "parent_skill_id": null,\n      "category_id": "calculation",\n      "definition": "既存の出題経路と問題定義に対応する技能。実際の珠操作を観測したという意味ではない。",\n      "observation_rule": "自動採点された回答・小段階の回答と支援イベントを別々に参照する。複合問題の誤答を全技能の誤りと断定しない。",\n      "prerequisite_skill_ids": null,\n      "progression_group_id": "soroban:tutorial:add",\n      "difficulty_axes": [\n        "difficulty_id"\n      ],\n      "is_active": true\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "skill",\n    "entry_id": "soroban:lesson:add5",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "skill_id": "soroban:lesson:add5",\n      "label": "2桁の繰り上がり",\n      "parent_skill_id": null,\n      "category_id": "calculation",\n      "definition": "既存の出題経路と問題定義に対応する技能。実際の珠操作を観測したという意味ではない。",\n      "observation_rule": "自動採点された回答・小段階の回答と支援イベントを別々に参照する。複合問題の誤答を全技能の誤りと断定しない。",\n      "prerequisite_skill_ids": null,\n      "progression_group_id": "soroban:tutorial:add",\n      "difficulty_axes": [\n        "difficulty_id"\n      ],\n      "is_active": true\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "skill",\n    "entry_id": "soroban:lesson:sub1",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "skill_id": "soroban:lesson:sub1",\n      "label": "そのまま引く",\n      "parent_skill_id": null,\n      "category_id": "calculation",\n      "definition": "既存の出題経路と問題定義に対応する技能。実際の珠操作を観測したという意味ではない。",\n      "observation_rule": "自動採点された回答・小段階の回答と支援イベントを別々に参照する。複合問題の誤答を全技能の誤りと断定しない。",\n      "prerequisite_skill_ids": null,\n      "progression_group_id": "soroban:tutorial:sub",\n      "difficulty_axes": [\n        "difficulty_id"\n      ],\n      "is_active": true\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "skill",\n    "entry_id": "soroban:lesson:sub2",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "skill_id": "soroban:lesson:sub2",\n      "label": "5珠から直接引く",\n      "parent_skill_id": null,\n      "category_id": "calculation",\n      "definition": "既存の出題経路と問題定義に対応する技能。実際の珠操作を観測したという意味ではない。",\n      "observation_rule": "自動採点された回答・小段階の回答と支援イベントを別々に参照する。複合問題の誤答を全技能の誤りと断定しない。",\n      "prerequisite_skill_ids": null,\n      "progression_group_id": "soroban:tutorial:sub",\n      "difficulty_axes": [\n        "difficulty_id"\n      ],\n      "is_active": true\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "skill",\n    "entry_id": "soroban:lesson:sub3",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "skill_id": "soroban:lesson:sub3",\n      "label": "5の補数で引く",\n      "parent_skill_id": null,\n      "category_id": "calculation",\n      "definition": "既存の出題経路と問題定義に対応する技能。実際の珠操作を観測したという意味ではない。",\n      "observation_rule": "自動採点された回答・小段階の回答と支援イベントを別々に参照する。複合問題の誤答を全技能の誤りと断定しない。",\n      "prerequisite_skill_ids": null,\n      "progression_group_id": "soroban:tutorial:sub",\n      "difficulty_axes": [\n        "difficulty_id"\n      ],\n      "is_active": true\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "skill",\n    "entry_id": "soroban:lesson:sub4",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "skill_id": "soroban:lesson:sub4",\n      "label": "10の補数で繰り下がる",\n      "parent_skill_id": null,\n      "category_id": "calculation",\n      "definition": "既存の出題経路と問題定義に対応する技能。実際の珠操作を観測したという意味ではない。",\n      "observation_rule": "自動採点された回答・小段階の回答と支援イベントを別々に参照する。複合問題の誤答を全技能の誤りと断定しない。",\n      "prerequisite_skill_ids": null,\n      "progression_group_id": "soroban:tutorial:sub",\n      "difficulty_axes": [\n        "difficulty_id"\n      ],\n      "is_active": true\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "skill",\n    "entry_id": "soroban:lesson:sub5",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "skill_id": "soroban:lesson:sub5",\n      "label": "2桁の繰り下がり",\n      "parent_skill_id": null,\n      "category_id": "calculation",\n      "definition": "既存の出題経路と問題定義に対応する技能。実際の珠操作を観測したという意味ではない。",\n      "observation_rule": "自動採点された回答・小段階の回答と支援イベントを別々に参照する。複合問題の誤答を全技能の誤りと断定しない。",\n      "prerequisite_skill_ids": null,\n      "progression_group_id": "soroban:tutorial:sub",\n      "difficulty_axes": [\n        "difficulty_id"\n      ],\n      "is_active": true\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "skill",\n    "entry_id": "soroban:lesson:mul1",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "skill_id": "soroban:lesson:mul1",\n      "label": "九九の答えを珠に置く",\n      "parent_skill_id": null,\n      "category_id": "calculation",\n      "definition": "既存の出題経路と問題定義に対応する技能。実際の珠操作を観測したという意味ではない。",\n      "observation_rule": "自動採点された回答・小段階の回答と支援イベントを別々に参照する。複合問題の誤答を全技能の誤りと断定しない。",\n      "prerequisite_skill_ids": null,\n      "progression_group_id": "soroban:tutorial:mul",\n      "difficulty_axes": [\n        "difficulty_id"\n      ],\n      "is_active": true\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "skill",\n    "entry_id": "soroban:lesson:mul2",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "skill_id": "soroban:lesson:mul2",\n      "label": "2桁×1桁の部分積",\n      "parent_skill_id": null,\n      "category_id": "calculation",\n      "definition": "既存の出題経路と問題定義に対応する技能。実際の珠操作を観測したという意味ではない。",\n      "observation_rule": "自動採点された回答・小段階の回答と支援イベントを別々に参照する。複合問題の誤答を全技能の誤りと断定しない。",\n      "prerequisite_skill_ids": null,\n      "progression_group_id": "soroban:tutorial:mul",\n      "difficulty_axes": [\n        "difficulty_id"\n      ],\n      "is_active": true\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "skill",\n    "entry_id": "soroban:lesson:mul3",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "skill_id": "soroban:lesson:mul3",\n      "label": "2桁×2桁",\n      "parent_skill_id": null,\n      "category_id": "calculation",\n      "definition": "既存の出題経路と問題定義に対応する技能。実際の珠操作を観測したという意味ではない。",\n      "observation_rule": "自動採点された回答・小段階の回答と支援イベントを別々に参照する。複合問題の誤答を全技能の誤りと断定しない。",\n      "prerequisite_skill_ids": null,\n      "progression_group_id": "soroban:tutorial:mul",\n      "difficulty_axes": [\n        "difficulty_id"\n      ],\n      "is_active": true\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "skill",\n    "entry_id": "soroban:lesson:mul4",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "skill_id": "soroban:lesson:mul4",\n      "label": "0がある数の位取り",\n      "parent_skill_id": null,\n      "category_id": "calculation",\n      "definition": "既存の出題経路と問題定義に対応する技能。実際の珠操作を観測したという意味ではない。",\n      "observation_rule": "自動採点された回答・小段階の回答と支援イベントを別々に参照する。複合問題の誤答を全技能の誤りと断定しない。",\n      "prerequisite_skill_ids": null,\n      "progression_group_id": "soroban:tutorial:mul",\n      "difficulty_axes": [\n        "difficulty_id"\n      ],\n      "is_active": true\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "skill",\n    "entry_id": "soroban:lesson:div1",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "skill_id": "soroban:lesson:div1",\n      "label": "1桁÷1桁",\n      "parent_skill_id": null,\n      "category_id": "calculation",\n      "definition": "既存の出題経路と問題定義に対応する技能。実際の珠操作を観測したという意味ではない。",\n      "observation_rule": "自動採点された回答・小段階の回答と支援イベントを別々に参照する。複合問題の誤答を全技能の誤りと断定しない。",\n      "prerequisite_skill_ids": null,\n      "progression_group_id": "soroban:tutorial:div",\n      "difficulty_axes": [\n        "difficulty_id"\n      ],\n      "is_active": true\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "skill",\n    "entry_id": "soroban:lesson:div2",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "skill_id": "soroban:lesson:div2",\n      "label": "2桁÷1桁",\n      "parent_skill_id": null,\n      "category_id": "calculation",\n      "definition": "既存の出題経路と問題定義に対応する技能。実際の珠操作を観測したという意味ではない。",\n      "observation_rule": "自動採点された回答・小段階の回答と支援イベントを別々に参照する。複合問題の誤答を全技能の誤りと断定しない。",\n      "prerequisite_skill_ids": null,\n      "progression_group_id": "soroban:tutorial:div",\n      "difficulty_axes": [\n        "difficulty_id"\n      ],\n      "is_active": true\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "skill",\n    "entry_id": "soroban:lesson:div3",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "skill_id": "soroban:lesson:div3",\n      "label": "3桁÷1桁",\n      "parent_skill_id": null,\n      "category_id": "calculation",\n      "definition": "既存の出題経路と問題定義に対応する技能。実際の珠操作を観測したという意味ではない。",\n      "observation_rule": "自動採点された回答・小段階の回答と支援イベントを別々に参照する。複合問題の誤答を全技能の誤りと断定しない。",\n      "prerequisite_skill_ids": null,\n      "progression_group_id": "soroban:tutorial:div",\n      "difficulty_axes": [\n        "difficulty_id"\n      ],\n      "is_active": true\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "skill",\n    "entry_id": "soroban:lesson:div4",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "skill_id": "soroban:lesson:div4",\n      "label": "2桁で割る",\n      "parent_skill_id": null,\n      "category_id": "calculation",\n      "definition": "既存の出題経路と問題定義に対応する技能。実際の珠操作を観測したという意味ではない。",\n      "observation_rule": "自動採点された回答・小段階の回答と支援イベントを別々に参照する。複合問題の誤答を全技能の誤りと断定しない。",\n      "prerequisite_skill_ids": null,\n      "progression_group_id": "soroban:tutorial:div",\n      "difficulty_axes": [\n        "difficulty_id"\n      ],\n      "is_active": true\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "skill",\n    "entry_id": "soroban:kuku:1",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "skill_id": "soroban:kuku:1",\n      "label": "soroban:kuku:1",\n      "parent_skill_id": null,\n      "category_id": "kuku",\n      "definition": "既存の出題経路と問題定義に対応する技能。実際の珠操作を観測したという意味ではない。",\n      "observation_rule": "自動採点された回答・小段階の回答と支援イベントを別々に参照する。複合問題の誤答を全技能の誤りと断定しない。",\n      "prerequisite_skill_ids": null,\n      "progression_group_id": "soroban:kuku:reading",\n      "difficulty_axes": [\n        "difficulty_id"\n      ],\n      "is_active": true\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "skill",\n    "entry_id": "soroban:kuku:2",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "skill_id": "soroban:kuku:2",\n      "label": "soroban:kuku:2",\n      "parent_skill_id": null,\n      "category_id": "kuku",\n      "definition": "既存の出題経路と問題定義に対応する技能。実際の珠操作を観測したという意味ではない。",\n      "observation_rule": "自動採点された回答・小段階の回答と支援イベントを別々に参照する。複合問題の誤答を全技能の誤りと断定しない。",\n      "prerequisite_skill_ids": null,\n      "progression_group_id": "soroban:kuku:reading",\n      "difficulty_axes": [\n        "difficulty_id"\n      ],\n      "is_active": true\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "skill",\n    "entry_id": "soroban:kuku:3",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "skill_id": "soroban:kuku:3",\n      "label": "soroban:kuku:3",\n      "parent_skill_id": null,\n      "category_id": "kuku",\n      "definition": "既存の出題経路と問題定義に対応する技能。実際の珠操作を観測したという意味ではない。",\n      "observation_rule": "自動採点された回答・小段階の回答と支援イベントを別々に参照する。複合問題の誤答を全技能の誤りと断定しない。",\n      "prerequisite_skill_ids": null,\n      "progression_group_id": "soroban:kuku:reading",\n      "difficulty_axes": [\n        "difficulty_id"\n      ],\n      "is_active": true\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "skill",\n    "entry_id": "soroban:kuku:4",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "skill_id": "soroban:kuku:4",\n      "label": "soroban:kuku:4",\n      "parent_skill_id": null,\n      "category_id": "kuku",\n      "definition": "既存の出題経路と問題定義に対応する技能。実際の珠操作を観測したという意味ではない。",\n      "observation_rule": "自動採点された回答・小段階の回答と支援イベントを別々に参照する。複合問題の誤答を全技能の誤りと断定しない。",\n      "prerequisite_skill_ids": null,\n      "progression_group_id": "soroban:kuku:reading",\n      "difficulty_axes": [\n        "difficulty_id"\n      ],\n      "is_active": true\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "skill",\n    "entry_id": "soroban:kuku:5",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "skill_id": "soroban:kuku:5",\n      "label": "soroban:kuku:5",\n      "parent_skill_id": null,\n      "category_id": "kuku",\n      "definition": "既存の出題経路と問題定義に対応する技能。実際の珠操作を観測したという意味ではない。",\n      "observation_rule": "自動採点された回答・小段階の回答と支援イベントを別々に参照する。複合問題の誤答を全技能の誤りと断定しない。",\n      "prerequisite_skill_ids": null,\n      "progression_group_id": "soroban:kuku:reading",\n      "difficulty_axes": [\n        "difficulty_id"\n      ],\n      "is_active": true\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "skill",\n    "entry_id": "soroban:kuku:6",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "skill_id": "soroban:kuku:6",\n      "label": "soroban:kuku:6",\n      "parent_skill_id": null,\n      "category_id": "kuku",\n      "definition": "既存の出題経路と問題定義に対応する技能。実際の珠操作を観測したという意味ではない。",\n      "observation_rule": "自動採点された回答・小段階の回答と支援イベントを別々に参照する。複合問題の誤答を全技能の誤りと断定しない。",\n      "prerequisite_skill_ids": null,\n      "progression_group_id": "soroban:kuku:reading",\n      "difficulty_axes": [\n        "difficulty_id"\n      ],\n      "is_active": true\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "skill",\n    "entry_id": "soroban:kuku:7",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "skill_id": "soroban:kuku:7",\n      "label": "soroban:kuku:7",\n      "parent_skill_id": null,\n      "category_id": "kuku",\n      "definition": "既存の出題経路と問題定義に対応する技能。実際の珠操作を観測したという意味ではない。",\n      "observation_rule": "自動採点された回答・小段階の回答と支援イベントを別々に参照する。複合問題の誤答を全技能の誤りと断定しない。",\n      "prerequisite_skill_ids": null,\n      "progression_group_id": "soroban:kuku:reading",\n      "difficulty_axes": [\n        "difficulty_id"\n      ],\n      "is_active": true\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "skill",\n    "entry_id": "soroban:kuku:8",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "skill_id": "soroban:kuku:8",\n      "label": "soroban:kuku:8",\n      "parent_skill_id": null,\n      "category_id": "kuku",\n      "definition": "既存の出題経路と問題定義に対応する技能。実際の珠操作を観測したという意味ではない。",\n      "observation_rule": "自動採点された回答・小段階の回答と支援イベントを別々に参照する。複合問題の誤答を全技能の誤りと断定しない。",\n      "prerequisite_skill_ids": null,\n      "progression_group_id": "soroban:kuku:reading",\n      "difficulty_axes": [\n        "difficulty_id"\n      ],\n      "is_active": true\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "skill",\n    "entry_id": "soroban:kuku:9",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "skill_id": "soroban:kuku:9",\n      "label": "soroban:kuku:9",\n      "parent_skill_id": null,\n      "category_id": "kuku",\n      "definition": "既存の出題経路と問題定義に対応する技能。実際の珠操作を観測したという意味ではない。",\n      "observation_rule": "自動採点された回答・小段階の回答と支援イベントを別々に参照する。複合問題の誤答を全技能の誤りと断定しない。",\n      "prerequisite_skill_ids": null,\n      "progression_group_id": "soroban:kuku:reading",\n      "difficulty_axes": [\n        "difficulty_id"\n      ],\n      "is_active": true\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "skill",\n    "entry_id": "soroban:complement:5",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "skill_id": "soroban:complement:5",\n      "label": "5の補数",\n      "parent_skill_id": null,\n      "category_id": "calculation",\n      "definition": "5の補数",\n      "observation_rule": "問題定義または小段階の回答として記録。最終誤答から原因は断定しない。",\n      "prerequisite_skill_ids": null,\n      "progression_group_id": "soroban:complement:5",\n      "difficulty_axes": [],\n      "is_active": true\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "skill",\n    "entry_id": "soroban:complement:10",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "skill_id": "soroban:complement:10",\n      "label": "10の補数",\n      "parent_skill_id": null,\n      "category_id": "calculation",\n      "definition": "10の補数",\n      "observation_rule": "問題定義または小段階の回答として記録。最終誤答から原因は断定しない。",\n      "prerequisite_skill_ids": null,\n      "progression_group_id": "soroban:complement:10",\n      "difficulty_axes": [],\n      "is_active": true\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "skill",\n    "entry_id": "soroban:mental_addition",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "skill_id": "soroban:mental_addition",\n      "label": "暗算の足し算",\n      "parent_skill_id": null,\n      "category_id": "calculation",\n      "definition": "暗算の足し算",\n      "observation_rule": "問題定義または小段階の回答として記録。最終誤答から原因は断定しない。",\n      "prerequisite_skill_ids": null,\n      "progression_group_id": "soroban:mental_addition",\n      "difficulty_axes": [],\n      "is_active": true\n    }\n  },\n  {\n    "schema_version": 1,\n    "source_app": "soroban",\n    "entry_type": "skill",\n    "entry_id": "soroban:mental_subtraction",\n    "content_version": "soroban-material-167",\n    "payload": {\n      "skill_id": "soroban:mental_subtraction",\n      "label": "暗算の引き算",\n      "parent_skill_id": null,\n      "category_id": "calculation",\n      "definition": "暗算の引き算",\n      "observation_rule": "問題定義または小段階の回答として記録。最終誤答から原因は断定しない。",\n      "prerequisite_skill_ids": null,\n      "progression_group_id": "soroban:mental_subtraction",\n      "difficulty_axes": [],\n      "is_active": true\n    }\n  }\n]'
CHOKOMANA_SAMPLE_JSON = '{\n  "test_fixture": true,\n  "events": [\n    {\n      "schema_version": 1,\n      "event_id": "9bf27d23-b30c-4a42-b483-dfc57ff00834",\n      "profile_id": "11111111-1111-4111-8111-111111111111",\n      "source_app": "soroban",\n      "app_version": "CLEAN-V171-DAILY-MEDAL-POPUP",\n      "content_version": "soroban-material-167",\n      "attempt_id": "4973d42e-966b-457a-ad74-ef2267b597dd",\n      "occurrence_id": null,\n      "question_id": null,\n      "segment_id": "5e1d0641-8f27-40bf-87a7-bcf4bad6c269",\n      "sequence": 1,\n      "occurred_at": "2026-11-07T14:59:55.000Z",\n      "event_type": "session_started",\n      "payload": {\n        "menu_id": "soroban:kuku:3",\n        "category_id": "kuku",\n        "difficulty_id": "3",\n        "progression_group_id": "soroban:kuku",\n        "mode": "challenge",\n        "original_mode": "上級",\n        "planned_question_count": 1,\n        "settings_snapshot": {\n          "voice_enabled": false,\n          "display_age": null,\n          "kanji_grade": null,\n          "time_limit_seconds": null,\n          "flash_interval_ms": null,\n          "input_method": "other",\n          "voice_rate": 1,\n          "narration_enabled": null,\n          "voice_answer_enabled": false\n        },\n        "trigger": "free",\n        "plan_item_id": null,\n        "parent_attempt_id": null,\n        "local_learner_id": "ad7201e9-e6ae-40b4-ba6a-efa09365cea9",\n        "identity_link_version": "launch-ticket-device-v1"\n      }\n    },\n    {\n      "schema_version": 1,\n      "event_id": "8f49c3dc-228b-4e42-ac22-9c2903f071e0",\n      "profile_id": "11111111-1111-4111-8111-111111111111",\n      "source_app": "soroban",\n      "app_version": "CLEAN-V171-DAILY-MEDAL-POPUP",\n      "content_version": "soroban-material-167",\n      "attempt_id": "4973d42e-966b-457a-ad74-ef2267b597dd",\n      "occurrence_id": "7b512472-01c7-44b9-b122-83f0b7373edf",\n      "question_id": "soroban:problem:v1:{\\"a\\":2,\\"op\\":\\"×\\",\\"b\\":9}",\n      "segment_id": "5e1d0641-8f27-40bf-87a7-bcf4bad6c269",\n      "sequence": 2,\n      "occurred_at": "2026-11-07T14:59:55.000Z",\n      "event_type": "item_presented",\n      "payload": {\n        "question_family_id": "soroban:kuku:3",\n        "skill_ids": [\n          "soroban:multiplication",\n          "soroban:kuku:2"\n        ],\n        "question_content_version": "soroban-material-167",\n        "position": 1,\n        "presentation_kind": "new",\n        "seen_in_local_history": false,\n        "parent_occurrence_id": null,\n        "retry_index": 0,\n        "answer_exposed_before": false,\n        "support_snapshot": {\n          "hint_count": 0,\n          "max_hint_step": null,\n          "explanation_seen": false,\n          "answer_seen": false,\n          "worked_example_seen": false,\n          "parent_help": null\n        },\n        "item_settings": {\n          "operand_digits": [\n            1,\n            1\n          ],\n          "term_count": 2,\n          "operators": null,\n          "complement_bases": null,\n          "carry": null,\n          "borrow": null,\n          "flash_interval_ms": null\n        },\n        "choice_order": null,\n        "input_method": "other",\n        "question_snapshot": {\n          "a": 2,\n          "b": 9,\n          "answer": 18\n        },\n        "lifetime_first_seen": "unknown",\n        "assessment_method": "automatic"\n      }\n    },\n    {\n      "schema_version": 1,\n      "event_id": "812db31a-c75a-4190-8b1c-a67b7d0d7295",\n      "profile_id": "11111111-1111-4111-8111-111111111111",\n      "source_app": "soroban",\n      "app_version": "CLEAN-V171-DAILY-MEDAL-POPUP",\n      "content_version": "soroban-material-167",\n      "attempt_id": "4973d42e-966b-457a-ad74-ef2267b597dd",\n      "occurrence_id": "7b512472-01c7-44b9-b122-83f0b7373edf",\n      "question_id": "soroban:problem:v1:{\\"a\\":2,\\"op\\":\\"×\\",\\"b\\":9}",\n      "segment_id": "5e1d0641-8f27-40bf-87a7-bcf4bad6c269",\n      "sequence": 3,\n      "occurred_at": "2026-11-07T15:00:00.000Z",\n      "event_type": "time_interval_closed",\n      "payload": {\n        "phase": "thinking",\n        "start_at": "2026-11-07T14:59:55.000Z",\n        "end_at": "2026-11-07T15:00:00.000Z",\n        "elapsed_ms": 5000,\n        "active_ms": 5000,\n        "excluded_ms": {\n          "hidden": 0,\n          "explicit_pause": 0,\n          "blocking_wait": 0\n        },\n        "exclusion_reason": null,\n        "timing_quality": "complete",\n        "window_instance_id": "401094ac-8ed6-46e1-ada9-b3a86ac09f06",\n        "substep_id": null\n      }\n    },\n    {\n      "schema_version": 1,\n      "event_id": "2ed983ed-c3f3-4e83-8c4d-0fb135b22784",\n      "profile_id": "11111111-1111-4111-8111-111111111111",\n      "source_app": "soroban",\n      "app_version": "CLEAN-V171-DAILY-MEDAL-POPUP",\n      "content_version": "soroban-material-167",\n      "attempt_id": "4973d42e-966b-457a-ad74-ef2267b597dd",\n      "occurrence_id": "7b512472-01c7-44b9-b122-83f0b7373edf",\n      "question_id": "soroban:problem:v1:{\\"a\\":2,\\"op\\":\\"×\\",\\"b\\":9}",\n      "segment_id": "5e1d0641-8f27-40bf-87a7-bcf4bad6c269",\n      "sequence": 4,\n      "occurred_at": "2026-11-07T15:00:00.000Z",\n      "event_type": "response_submitted",\n      "payload": {\n        "response_id": "5714d93a-1962-4ad1-bdd2-f943e850a0ea",\n        "skill_ids": null,\n        "observation_scope": "whole_item_unlocalized",\n        "response_index": 1,\n        "substep_id": null,\n        "response_value": 17,\n        "response_status": "answered",\n        "input_method": "other",\n        "assessment_method": "automatic",\n        "is_correct": false,\n        "correctness_basis": "existing_app_evaluator",\n        "rubric_id": "soroban:kuku:3",\n        "rubric_version": "soroban-material-167",\n        "evaluator_version": "soroban-163",\n        "support_before_response": {\n          "hint_count": 0,\n          "max_hint_step": null,\n          "explanation_seen": false,\n          "answer_seen": false,\n          "worked_example_seen": false,\n          "parent_help": null\n        },\n        "answer_latency_ms": 5000,\n        "timing_quality": "complete",\n        "speech_status": "not_used",\n        "supersedes_response_id": null,\n        "reason_response": null,\n        "observed_error_code": null,\n        "inferred_error": null,\n        "expected_value": null\n      }\n    },\n    {\n      "schema_version": 1,\n      "event_id": "2c9cc737-ac0a-4796-a63b-4236f896b7a2",\n      "profile_id": "11111111-1111-4111-8111-111111111111",\n      "source_app": "soroban",\n      "app_version": "CLEAN-V171-DAILY-MEDAL-POPUP",\n      "content_version": "soroban-material-167",\n      "attempt_id": "4973d42e-966b-457a-ad74-ef2267b597dd",\n      "occurrence_id": "7b512472-01c7-44b9-b122-83f0b7373edf",\n      "question_id": "soroban:problem:v1:{\\"a\\":2,\\"op\\":\\"×\\",\\"b\\":9}",\n      "segment_id": "5e1d0641-8f27-40bf-87a7-bcf4bad6c269",\n      "sequence": 5,\n      "occurred_at": "2026-11-07T15:00:00.000Z",\n      "event_type": "support_used",\n      "payload": {\n        "support_type": "hint",\n        "substep_id": null,\n        "step": null,\n        "support_id": "soroban:kuku:3:hint",\n        "support_version": "soroban-material-167",\n        "before_first_response": false,\n        "answer_revealing": true,\n        "requested_at": "2026-11-07T15:00:00.000Z"\n      }\n    },\n    {\n      "schema_version": 1,\n      "event_id": "316b69fe-53f5-4e26-89b2-75eebda42a9a",\n      "profile_id": "11111111-1111-4111-8111-111111111111",\n      "source_app": "soroban",\n      "app_version": "CLEAN-V171-DAILY-MEDAL-POPUP",\n      "content_version": "soroban-material-167",\n      "attempt_id": "4973d42e-966b-457a-ad74-ef2267b597dd",\n      "occurrence_id": "7b512472-01c7-44b9-b122-83f0b7373edf",\n      "question_id": "soroban:problem:v1:{\\"a\\":2,\\"op\\":\\"×\\",\\"b\\":9}",\n      "segment_id": "5e1d0641-8f27-40bf-87a7-bcf4bad6c269",\n      "sequence": 6,\n      "occurred_at": "2026-11-07T15:00:00.000Z",\n      "event_type": "support_used",\n      "payload": {\n        "support_type": "explanation",\n        "substep_id": null,\n        "step": null,\n        "support_id": "soroban:kuku:3:explanation",\n        "support_version": "soroban-material-167",\n        "before_first_response": false,\n        "answer_revealing": true,\n        "requested_at": "2026-11-07T15:00:00.000Z"\n      }\n    },\n    {\n      "schema_version": 1,\n      "event_id": "425544fb-ddb8-4a89-abd6-9c1dd6f10e72",\n      "profile_id": "11111111-1111-4111-8111-111111111111",\n      "source_app": "soroban",\n      "app_version": "CLEAN-V171-DAILY-MEDAL-POPUP",\n      "content_version": "soroban-material-167",\n      "attempt_id": "4973d42e-966b-457a-ad74-ef2267b597dd",\n      "occurrence_id": "7b512472-01c7-44b9-b122-83f0b7373edf",\n      "question_id": "soroban:problem:v1:{\\"a\\":2,\\"op\\":\\"×\\",\\"b\\":9}",\n      "segment_id": "5e1d0641-8f27-40bf-87a7-bcf4bad6c269",\n      "sequence": 7,\n      "occurred_at": "2026-11-07T15:00:02.000Z",\n      "event_type": "time_interval_closed",\n      "payload": {\n        "phase": "explanation",\n        "start_at": "2026-11-07T15:00:00.000Z",\n        "end_at": "2026-11-07T15:00:02.000Z",\n        "elapsed_ms": 2000,\n        "active_ms": 2000,\n        "excluded_ms": {\n          "hidden": 0,\n          "explicit_pause": 0,\n          "blocking_wait": 0\n        },\n        "exclusion_reason": null,\n        "timing_quality": "complete",\n        "window_instance_id": "401094ac-8ed6-46e1-ada9-b3a86ac09f06",\n        "substep_id": null\n      }\n    },\n    {\n      "schema_version": 1,\n      "event_id": "8cf07f60-5b07-4e4f-ab66-d7fc82cbf9cd",\n      "profile_id": "11111111-1111-4111-8111-111111111111",\n      "source_app": "soroban",\n      "app_version": "CLEAN-V171-DAILY-MEDAL-POPUP",\n      "content_version": "soroban-material-167",\n      "attempt_id": "4973d42e-966b-457a-ad74-ef2267b597dd",\n      "occurrence_id": null,\n      "question_id": null,\n      "segment_id": "5e1d0641-8f27-40bf-87a7-bcf4bad6c269",\n      "sequence": 8,\n      "occurred_at": "2026-11-07T15:00:02.000Z",\n      "event_type": "session_paused",\n      "payload": {\n        "reason": "tab_visibility",\n        "suspended_occurrence_id": "7b512472-01c7-44b9-b122-83f0b7373edf",\n        "last_response_id": null\n      }\n    },\n    {\n      "schema_version": 1,\n      "event_id": "df4ff943-b75f-4507-a6f7-d3414fdf9ddc",\n      "profile_id": "11111111-1111-4111-8111-111111111111",\n      "source_app": "soroban",\n      "app_version": "CLEAN-V171-DAILY-MEDAL-POPUP",\n      "content_version": "soroban-material-167",\n      "attempt_id": "4973d42e-966b-457a-ad74-ef2267b597dd",\n      "occurrence_id": "7b512472-01c7-44b9-b122-83f0b7373edf",\n      "question_id": "soroban:problem:v1:{\\"a\\":2,\\"op\\":\\"×\\",\\"b\\":9}",\n      "segment_id": "5e1d0641-8f27-40bf-87a7-bcf4bad6c269",\n      "sequence": 9,\n      "occurred_at": "2026-11-07T15:00:05.000Z",\n      "event_type": "time_interval_closed",\n      "payload": {\n        "phase": "explanation",\n        "start_at": "2026-11-07T15:00:02.000Z",\n        "end_at": "2026-11-07T15:00:05.000Z",\n        "elapsed_ms": 3000,\n        "active_ms": 0,\n        "excluded_ms": {\n          "hidden": 3000,\n          "explicit_pause": 0,\n          "blocking_wait": 0\n        },\n        "exclusion_reason": "tab_hidden",\n        "timing_quality": "complete",\n        "window_instance_id": "401094ac-8ed6-46e1-ada9-b3a86ac09f06",\n        "substep_id": null\n      }\n    },\n    {\n      "schema_version": 1,\n      "event_id": "a8e07adb-0dc2-4d92-8578-09f88ca60863",\n      "profile_id": "11111111-1111-4111-8111-111111111111",\n      "source_app": "soroban",\n      "app_version": "CLEAN-V171-DAILY-MEDAL-POPUP",\n      "content_version": "soroban-material-167",\n      "attempt_id": "4973d42e-966b-457a-ad74-ef2267b597dd",\n      "occurrence_id": null,\n      "question_id": null,\n      "segment_id": "5e1d0641-8f27-40bf-87a7-bcf4bad6c269",\n      "sequence": 10,\n      "occurred_at": "2026-11-07T15:00:05.000Z",\n      "event_type": "session_resumed",\n      "payload": {\n        "reason": "tab_visibility",\n        "suspended_occurrence_id": "7b512472-01c7-44b9-b122-83f0b7373edf",\n        "last_response_id": null\n      }\n    },\n    {\n      "schema_version": 1,\n      "event_id": "dcab9632-631a-49b2-8409-62c24f34a2a0",\n      "profile_id": "11111111-1111-4111-8111-111111111111",\n      "source_app": "soroban",\n      "app_version": "CLEAN-V171-DAILY-MEDAL-POPUP",\n      "content_version": "soroban-material-167",\n      "attempt_id": "4973d42e-966b-457a-ad74-ef2267b597dd",\n      "occurrence_id": "7b512472-01c7-44b9-b122-83f0b7373edf",\n      "question_id": "soroban:problem:v1:{\\"a\\":2,\\"op\\":\\"×\\",\\"b\\":9}",\n      "segment_id": "5e1d0641-8f27-40bf-87a7-bcf4bad6c269",\n      "sequence": 11,\n      "occurred_at": "2026-11-07T15:00:07.000Z",\n      "event_type": "time_interval_closed",\n      "payload": {\n        "phase": "thinking",\n        "start_at": "2026-11-07T15:00:05.000Z",\n        "end_at": "2026-11-07T15:00:07.000Z",\n        "elapsed_ms": 2000,\n        "active_ms": 0,\n        "excluded_ms": {\n          "hidden": 0,\n          "explicit_pause": 2000,\n          "blocking_wait": 0\n        },\n        "exclusion_reason": "explicit_pause",\n        "timing_quality": "complete",\n        "window_instance_id": "401094ac-8ed6-46e1-ada9-b3a86ac09f06",\n        "substep_id": null\n      }\n    },\n    {\n      "schema_version": 1,\n      "event_id": "9f85bc7d-d16b-4b94-bccc-3d94844b7507",\n      "profile_id": "11111111-1111-4111-8111-111111111111",\n      "source_app": "soroban",\n      "app_version": "CLEAN-V171-DAILY-MEDAL-POPUP",\n      "content_version": "soroban-material-167",\n      "attempt_id": "4973d42e-966b-457a-ad74-ef2267b597dd",\n      "occurrence_id": "7b512472-01c7-44b9-b122-83f0b7373edf",\n      "question_id": "soroban:problem:v1:{\\"a\\":2,\\"op\\":\\"×\\",\\"b\\":9}",\n      "segment_id": "5e1d0641-8f27-40bf-87a7-bcf4bad6c269",\n      "sequence": 12,\n      "occurred_at": "2026-11-07T15:00:07.000Z",\n      "event_type": "response_submitted",\n      "payload": {\n        "response_id": "7ac9bd44-9195-464e-8e84-ef0e1fa2f9c8",\n        "skill_ids": null,\n        "observation_scope": "whole_item_unlocalized",\n        "response_index": 2,\n        "substep_id": null,\n        "response_value": 18,\n        "response_status": "answered",\n        "input_method": "other",\n        "assessment_method": "automatic",\n        "is_correct": true,\n        "correctness_basis": "existing_app_evaluator",\n        "rubric_id": "soroban:kuku:3",\n        "rubric_version": "soroban-material-167",\n        "evaluator_version": "soroban-163",\n        "support_before_response": {\n          "hint_count": 1,\n          "max_hint_step": null,\n          "explanation_seen": true,\n          "answer_seen": false,\n          "worked_example_seen": false,\n          "parent_help": null\n        },\n        "answer_latency_ms": 5000,\n        "timing_quality": "complete",\n        "speech_status": "not_used",\n        "supersedes_response_id": null,\n        "reason_response": null,\n        "observed_error_code": null,\n        "inferred_error": null,\n        "expected_value": null\n      }\n    },\n    {\n      "schema_version": 1,\n      "event_id": "9afcb343-c5c8-4671-9e7f-b6e7e7cfe8a7",\n      "profile_id": "11111111-1111-4111-8111-111111111111",\n      "source_app": "soroban",\n      "app_version": "CLEAN-V171-DAILY-MEDAL-POPUP",\n      "content_version": "soroban-material-167",\n      "attempt_id": "4973d42e-966b-457a-ad74-ef2267b597dd",\n      "occurrence_id": "7b512472-01c7-44b9-b122-83f0b7373edf",\n      "question_id": "soroban:problem:v1:{\\"a\\":2,\\"op\\":\\"×\\",\\"b\\":9}",\n      "segment_id": "5e1d0641-8f27-40bf-87a7-bcf4bad6c269",\n      "sequence": 13,\n      "occurred_at": "2026-11-07T15:00:08.000Z",\n      "event_type": "time_interval_closed",\n      "payload": {\n        "phase": "feedback",\n        "start_at": "2026-11-07T15:00:07.000Z",\n        "end_at": "2026-11-07T15:00:08.000Z",\n        "elapsed_ms": 1000,\n        "active_ms": 1000,\n        "excluded_ms": {\n          "hidden": 0,\n          "explicit_pause": 0,\n          "blocking_wait": 0\n        },\n        "exclusion_reason": null,\n        "timing_quality": "complete",\n        "window_instance_id": "401094ac-8ed6-46e1-ada9-b3a86ac09f06",\n        "substep_id": null\n      }\n    },\n    {\n      "schema_version": 1,\n      "event_id": "78dbb18e-24d7-4868-8e75-a0872ca7c0e7",\n      "profile_id": "11111111-1111-4111-8111-111111111111",\n      "source_app": "soroban",\n      "app_version": "CLEAN-V171-DAILY-MEDAL-POPUP",\n      "content_version": "soroban-material-167",\n      "attempt_id": "4973d42e-966b-457a-ad74-ef2267b597dd",\n      "occurrence_id": "7b512472-01c7-44b9-b122-83f0b7373edf",\n      "question_id": "soroban:problem:v1:{\\"a\\":2,\\"op\\":\\"×\\",\\"b\\":9}",\n      "segment_id": "5e1d0641-8f27-40bf-87a7-bcf4bad6c269",\n      "sequence": 14,\n      "occurred_at": "2026-11-07T15:00:08.000Z",\n      "event_type": "session_ended",\n      "payload": {\n        "status": "completed",\n        "planned_question_count": 1,\n        "presented_count": 1,\n        "answered_count": 1,\n        "last_occurrence_id": "7b512472-01c7-44b9-b122-83f0b7373edf",\n        "last_response_id": "7ac9bd44-9195-464e-8e84-ef0e1fa2f9c8",\n        "original_result": {\n          "correct_count": 0,\n          "total_count": 1,\n          "grade": "white"\n        }\n      }\n    }\n  ]\n}'
import sys as _cm_sys
if __name__ == '__main__' and len(_cm_sys.argv)>1 and _cm_sys.argv[1] in ('--chokomana-sql','--chokomana-spec','--chokomana-consumer','--chokomana-catalog','--chokomana-sample'):
    print(CHOKOMANA_SETUP_SQL if _cm_sys.argv[1]=='--chokomana-sql' else CHOKOMANA_REFERENCE_PY if _cm_sys.argv[1]=='--chokomana-consumer' else CHOKOMANA_CATALOG_JSON if _cm_sys.argv[1]=='--chokomana-catalog' else CHOKOMANA_SAMPLE_JSON if _cm_sys.argv[1]=='--chokomana-sample' else CHOKOMANA_SPEC)
    raise SystemExit(0)

import json
import hashlib
import tempfile
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from supabase import create_client


st.set_page_config(
    page_title="そろばん",
    page_icon="🧮",
    layout="wide",
)

APP_VERSION = "CLEAN-V171-DAILY-MEDAL-POPUP"
BUCKET_NAME = "music"
SIGNED_URL_EXPIRES_IN = 3600

BGM_FILES = [
    "1.mp3", "2.mp3", "3.mp3",
    "4.mp3", "5.mp3", "6.mp3",
    "7.mp3", "8.mp3", "9.mp3",
    "10-1.mp3", "10-2.mp3", "10-3.mp3",
]



@st.cache_resource
def get_supabase():
    return create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_SERVICE_ROLE_KEY"],
    )


@st.cache_data(ttl=3000, show_spinner=False)
def get_bgm_urls():
    bucket = get_supabase().storage.from_(BUCKET_NAME)
    urls = {}

    for filename in BGM_FILES:
        result = bucket.create_signed_url(filename, SIGNED_URL_EXPIRES_IN)

        if isinstance(result, dict):
            signed_url = (
                result.get("signedURL")
                or result.get("signedUrl")
                or result.get("signed_url")
            )
        else:
            signed_url = (
                getattr(result, "signedURL", None)
                or getattr(result, "signedUrl", None)
                or getattr(result, "signed_url", None)
            )

        if not signed_url:
            raise RuntimeError(f"{filename} のSigned URLを取得できませんでした。")

        urls[filename] = signed_url

    return urls




try:
    BGM_URLS = get_bgm_urls()
except KeyError:
    st.error(
        "Streamlit Secrets に SUPABASE_URL と "
        "SUPABASE_SERVICE_ROLE_KEY を設定してください。"
    )
    st.stop()
except Exception as exc:
    st.error("Supabase Storage のBGMを取得できませんでした。")
    st.caption(str(exc))
    st.stop()


BGM_JSON = json.dumps(BGM_URLS, ensure_ascii=False)
VERSION_JSON = json.dumps(APP_VERSION)
KUKU_GOLD_MEDAL_URI = 'data:image/webp;base64,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'
KUKU_SILVER_MEDAL_URI = 'data:image/webp;base64,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'
KUKU_BRONZE_MEDAL_URI = 'data:image/webp;base64,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'

HTML = r"""
<div id="soroban-app">
<style>
  * { box-sizing: border-box; }

  body {
    margin: 0;
    background: #f7f5ef;
    color: #24231f;
    font-family: system-ui, -apple-system, "Hiragino Sans", "Yu Gothic", sans-serif;
  }

  #soroban-app {
    max-width: 1180px;
    margin: 0 auto;
    padding: 16px;
  }

  button, input { font: inherit; }

  button {
    min-height: 46px;
    border: 0;
    border-radius: 12px;
    padding: 10px 16px;
    cursor: pointer;
    font-weight: 800;
    color: #24231f;
    background: #e9e4da;
    touch-action: manipulation;
  }

  button.primary {
    background: #315f86;
    color: #fff;
  }

  button:disabled {
    opacity: .45;
    cursor: not-allowed;
  }

  .version {
    font-size: 11px;
    color: #8a857c;
    margin-bottom: 8px;
  }

  .home-version-footer {
    margin-top: 18px;
    padding: 6px 2px 2px;
    color: #a09a90;
    font-size: 9px;
    text-align: center;
    letter-spacing: .02em;
  }

  /* =====================================================
     APP TOP
     ===================================================== */
  .app-home {
    padding: 8px 0 12px;
  }

  .home-hub-nav { display: flex; justify-content: flex-start; margin-bottom: 8px; }
  .home-hub-nav a {
    display: inline-flex; align-items: center; box-sizing: border-box;
    min-height: 46px; max-width: 100%; padding: 10px 16px;
    border-radius: 12px; background: #e9e4da; color: #24231f;
    font: inherit; font-weight: 800; text-decoration: none;
    overflow-wrap: anywhere; touch-action: manipulation;
  }
  .home-hub-nav a:focus-visible { outline: 3px solid #315f86; outline-offset: 3px; }

  .home-title {
    margin: 6px 0 8px;
    text-align: center;
    font-size: clamp(26px, 5vw, 42px);
    font-weight: 1000;
    letter-spacing: .02em;
  }

  .home-sub {
    margin: 0 auto 22px;
    max-width: 760px;
    text-align: center;
    color: #6d675f;
    font-size: 14px;
    line-height: 1.7;
  }

  .home-mode-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 16px;
    margin-top: 6px;
  }

  .home-weakness-btn {
    width: 100%;
    min-height: 92px;
    display: grid;
    grid-template-columns: auto 1fr auto;
    align-items: center;
    gap: 12px;
    margin: 0 0 14px;
    padding: 14px 18px;
    border: 2px solid #cba769;
    border-radius: 18px;
    background: #fff9ec;
    color: #443a2c;
    text-align: left;
    box-shadow: 0 6px 18px rgba(81, 61, 25, .07);
  }

  .home-weakness-icon {
    font-size: 27px;
  }

  .home-weakness-copy strong {
    display: block;
    font-size: 18px;
  }

  .home-weakness-copy span {
    display: block;
    margin-top: 3px;
    color: #71614c;
    font-size: 11px;
    line-height: 1.45;
  }

  .home-weakness-arrow {
    font-size: 22px;
    font-weight: 1000;
  }

  .weakness-view {
    display: none;
  }

  /* 学習モードは現在TOPから使用しない。実装コードは保守用に残す。 */
  #learningView {
    display: none !important;
  }

  .home-mode-btn.weakness-home {
    background: #fff9ec;
    border-color: #cba769;
  }

  .weakness-view.show {
    display: block;
  }

  .challenge-operation-nav {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 8px;
    margin: 14px 0 18px;
  }

  .challenge-operation-nav button {
    min-height: 46px;
    padding: 8px 6px;
    border: 1px solid #d4ccbf;
    border-radius: 12px;
    background: #fff;
    font-size: 13px;
    font-weight: 950;
  }

  .challenge-operation-nav button:hover {
    border-color: #9cb3c5;
    background: #f4f9fc;
  }

  .mode-section-anchor {
    scroll-margin-top: 86px;
  }

  .rank-goal-summary {
    margin-top: 8px;
    font-size: 12px;
    font-weight: 900;
    line-height: 1.55;
    color: #5b5142;
  }

  .rank-goal-list {
    display: grid;
    gap: 8px;
    margin-top: 10px;
  }

  .rank-goal-row {
    display: grid;
    grid-template-columns: 72px minmax(0, 1fr) auto;
    align-items: center;
    gap: 9px;
    padding: 10px 11px;
    border: 1px solid #e0d5bd;
    border-radius: 12px;
    background: #fff;
  }

  .rank-goal-row.done {
    border-color: #b7cfba;
    background: #f3faf4;
  }

  .rank-goal-op {
    font-size: 12px;
    font-weight: 1000;
    color: #3f5261;
  }

  .rank-goal-mode {
    min-width: 0;
    font-size: 11px;
    line-height: 1.4;
    color: #665f56;
  }

  .rank-goal-status {
    white-space: nowrap;
    padding: 5px 8px;
    border-radius: 999px;
    background: #f6ead0;
    color: #76571e;
    font-size: 10px;
    font-weight: 1000;
  }

  .rank-goal-row.done .rank-goal-status {
    background: #dfeee1;
    color: #35603c;
  }

  .weakness-group {
    margin-top: 18px;
  }

  .weakness-group-title {
    margin: 0 0 9px;
    font-size: 19px;
    font-weight: 1000;
  }

  .weakness-mode-card.unavailable {
    opacity: .64;
    background: #f6f4ef;
  }

  .restart-challenge-btn {
    border-color: #d4ae68;
    background: #fff7e7;
    color: #654a1d;
    font-weight: 950;
  }

  /* 動画での振り返りは現在使わない。機能コードは残すがUIと起動経路を無効化。 */
  .analysis-control,
  #cameraSetupModal,
  #videoReviewPanel,
  #recordingBadge {
    display: none !important;
  }


  .home-rank-track-grid {
    width: min(920px, 100%);
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px;
    margin: 0 auto 34px;
  }

  .home-rank-card {
    width: 100%;
    min-width: 0;
    display: flex;
    align-items: center;
    justify-content: flex-start;
    gap: 12px;
    margin: 0;
    padding: 12px 14px;
    border: 1px solid #d9cfb8;
    border-radius: 18px;
    background: linear-gradient(135deg, #fffdf7, #f4eddc);
    box-shadow: 0 8px 22px rgba(74, 60, 35, .08);
  }

  .home-rank-card.addsub-track {
    border-color: #d6bd86;
    background: linear-gradient(135deg, #fffdf7, #f7edd6);
  }

  .home-rank-card.muldiv-track {
    border-color: #aebfd0;
    background: linear-gradient(135deg, #fbfdff, #eaf1f7);
  }

  .home-rank-copy {
    min-width: 0;
  }

  .home-rank-label {
    color: #786d5a;
    font-size: 10px;
    font-weight: 900;
    letter-spacing: .08em;
  }

  .home-rank-name {
    margin-top: 2px;
    font-size: 22px;
    font-weight: 1000;
  }

  /* TOPの現在階級メダルは、九九と同じひもなしの丸いコイン型。 */
  .home-rank-medal-coin {
    position: relative;
    width: 78px;
    height: 78px;
    flex: 0 0 78px;
    display: grid;
    place-items: center;
  }

  .home-rank-medal-image {
    display: block;
    width: 78px;
    height: 78px;
    object-fit: contain;
    filter: drop-shadow(0 4px 5px rgba(55, 42, 27, .28));
  }

  .home-rank-medal-placeholder {
    display: none;
    width: 68px;
    height: 68px;
    place-items: center;
    border: 3px solid #aaa297;
    border-radius: 50%;
    background:
      radial-gradient(circle at 35% 28%, #f0ece4 0%, #d8d3ca 62%, #b8b1a6 100%);
    color: #6f685f;
    box-shadow:
      inset 0 0 0 4px rgba(255,255,255,.32),
      0 3px 5px rgba(55,45,34,.13);
    font-size: 22px;
    font-weight: 1000;
  }

  .home-rank-medal-coin.no-rank .home-rank-medal-image {
    display: none;
  }

  .home-rank-medal-coin.no-rank .home-rank-medal-placeholder {
    display: grid;
  }

  .rank-medal {
    --medal-face: #b77a4e;
    --medal-edge: #795036;
    --medal-text: #34251b;
    --ribbon-left: #365f87;
    --ribbon-right: #9b4c4d;

    position: relative;
    isolation: isolate;
    overflow: visible;
    width: 62px;
    height: 62px;
    flex: 0 0 62px;
    display: grid;
    place-items: center;
    border: 3px solid var(--medal-edge);
    border-radius: 50%;
    background: var(--medal-face);
    color: var(--medal-text);
    box-shadow: 0 3px 0 rgba(55, 45, 34, .14);
    text-align: center;
    font-weight: 1000;
    line-height: 1;
  }

  .rank-medal::before,
  .rank-medal::after {
    content: "";
    position: absolute;
    z-index: -1;
    top: 45px;
    width: 23px;
    height: 42px;
    clip-path: polygon(0 0, 100% 0, 100% 76%, 74% 100%, 50% 83%, 26% 100%, 0 76%);
  }

  .rank-medal::before {
    left: 6px;
    background: var(--ribbon-left);
    transform: rotate(7deg);
    transform-origin: top center;
  }

  .rank-medal::after {
    right: 6px;
    background: var(--ribbon-right);
    transform: rotate(-7deg);
    transform-origin: top center;
  }

  .rank-medal-text {
    position: relative;
    z-index: 2;
    max-width: 52px;
    font-size: 12px;
    text-shadow: none;
  }

  .rank-medal-text::before {
    content: "";
    position: absolute;
    inset: -13px -11px;
    z-index: -1;
    border: 1px solid currentColor;
    border-radius: 50%;
    opacity: .28;
  }

  .rank-medal.no-rank {
    --medal-face: #d8d3ca;
    --medal-edge: #aaa297;
    --medal-text: #6f685f;
    box-shadow: 0 2px 0 rgba(55, 45, 34, .10);
  }

  .rank-medal.no-rank::before,
  .rank-medal.no-rank::after {
    display: none;
  }

  .rank-medal.rank-kyu-low {
    --medal-face: #b77a4e;
    --medal-edge: #795036;
    --medal-text: #34251b;
  }

  .rank-medal.rank-kyu-mid {
    --medal-face: #bdc3c8;
    --medal-edge: #78818a;
    --medal-text: #2f353a;
  }

  .rank-medal.rank-kyu-high {
    --medal-face: #d2aa3c;
    --medal-edge: #8d6d1d;
    --medal-text: #3b3014;
  }

  .rank-medal.rank-dan-1 {
    --medal-face: #b96b43;
    --medal-edge: #7c462d;
    --medal-text: #342116;
  }

  .rank-medal.rank-dan-2 {
    --medal-face: #d4d8db;
    --medal-edge: #7e8790;
    --medal-text: #30363b;
  }

  .rank-medal.rank-dan-3 {
    --medal-face: #d4a92f;
    --medal-edge: #876817;
    --medal-text: #392e11;
  }

  .rank-medal.rank-master {
    --medal-face: #315d80;
    --medal-edge: #c8a044;
    --medal-text: #ffffff;
    --ribbon-left: #243e63;
    --ribbon-right: #8f3d46;
    box-shadow: 0 3px 0 rgba(38, 51, 67, .18);
  }

  /* メダル色は級・段ではなく達成段階で統一する。 */
  .rank-medal.medal-bronze {
    --medal-face: #b87333;
    --medal-edge: #75451f;
    --medal-text: #2f1d11;
    --ribbon-left: #7a5134;
    --ribbon-right: #a46e45;
  }

  .rank-medal.medal-silver {
    --medal-face: #d7dbe0;
    --medal-edge: #7d8791;
    --medal-text: #30363b;
    --ribbon-left: #66727d;
    --ribbon-right: #a0a9b1;
  }

  .rank-medal.medal-gold {
    --medal-face: #e0b52f;
    --medal-edge: #8a6917;
    --medal-text: #342a10;
    --ribbon-left: #8a6c1e;
    --ribbon-right: #c39a24;
    box-shadow: 0 3px 0 rgba(83, 65, 18, .18);
  }

  .home-mode-btn {
    min-height: 168px;
    padding: 22px 18px;
    border: 2px solid #d6cfc2;
    border-radius: 22px;
    background: #fff;
    text-align: left;
    box-shadow: 0 8px 24px rgba(60, 50, 40, .07);
  }

  .home-mode-btn.primary-home {
    background: #315f86;
    color: #fff;
    border-color: #315f86;
  }

  .home-mode-kicker {
    display: block;
    margin-bottom: 10px;
    font-size: 11px;
    font-weight: 950;
    letter-spacing: .1em;
    opacity: .72;
  }

  .home-mode-name {
    display: block;
    margin-bottom: 9px;
    font-size: clamp(22px, 4vw, 32px);
    font-weight: 1000;
  }

  .home-mode-desc {
    display: block;
    font-size: 13px;
    line-height: 1.6;
    opacity: .86;
  }

  .home-mode-btn.anzan-home {
    background: #fff8e8;
    border-color: #e2d2a9;
  }

  .home-mode-btn.settings-home {
    background: #f4f1ec;
    border-color: #d8d1c6;
  }

  /* =====================================================
     KUKU INSTANT CHALLENGE
     ===================================================== */
  .kuku-view { display: none; }
  .kuku-view.show { display: block; }
  .home-mode-btn.kuku-home { background: #f3f8ff; border-color: #a9bfd3; }
  .kuku-hero { padding: 18px; border: 1px solid #dcd5c8; border-radius: 20px; background: #fff; }
  .kuku-hero h2 { margin: 0 0 7px; font-size: clamp(24px, 4vw, 34px); }
  .kuku-hero p { margin: 0; color: #6b655d; font-size: 13px; line-height: 1.7; }
  .kuku-level-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin-top: 16px; }
  .kuku-level-card { display: flex; flex-direction: column; min-height: 220px; padding: 16px; border: 1px solid #ddd7ca; border-radius: 18px; background: #fff; }
  .kuku-level-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
  .kuku-level-no { color: #77889a; font-size: 11px; font-weight: 950; letter-spacing: .08em; }
  .kuku-level-name { margin: 7px 0; font-size: 20px; font-weight: 1000; }
  .kuku-level-desc { flex: 1; color: #6d675f; font-size: 12px; line-height: 1.6; }
  .kuku-level-meta { margin: 9px 0; color: #49657d; font-size: 11px; font-weight: 950; }
  .kuku-medal-strip {
    display: flex;
    align-items: flex-start;
    justify-content: flex-end;
    gap: 7px;
    flex-wrap: nowrap;
    margin-left: auto;
  }
  .kuku-medal-chip {
    display: inline-grid;
    grid-template-rows: 44px auto;
    justify-items: center;
    align-items: center;
    gap: 1px;
    min-width: 44px;
    padding: 0;
    border: 0;
    background: transparent;
    color: #4e4840;
    line-height: 1;
  }
  .kuku-medal-image {
    display: block;
    width: 44px;
    height: 44px;
    object-fit: contain;
    filter: drop-shadow(0 2px 3px rgba(55, 42, 27, .24));
  }
  .kuku-medal-chip .count {
    min-width: 2.4em;
    padding: 2px 5px;
    border: 1px solid #ddd5c8;
    border-radius: 999px;
    background: rgba(255,255,255,.92);
    color: #39342e;
    text-align: center;
    font-size: 11px;
    font-weight: 1000;
    font-variant-numeric: tabular-nums;
  }
  @media (max-width: 640px) {
    .kuku-medal-strip { gap: 5px; }
    .kuku-medal-chip { grid-template-rows: 38px auto; min-width: 38px; }
    .kuku-medal-image { width: 38px; height: 38px; }
    .kuku-medal-chip .count { font-size: 10px; }
  }
  .kuku-game-card, .kuku-result-card { margin-top: 14px; padding: 18px; border: 2px solid #ddd7ca; border-radius: 22px; background: #fff; text-align: center; }
  .kuku-status { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 8px; color: #6e685f; font-size: 12px; font-weight: 900; }
  .kuku-status > :first-child { text-align: left; }
  .kuku-status > :last-child { text-align: right; }
  .kuku-timer { min-width: 72px; font-size: 25px; font-weight: 1000; color: #315f86; font-variant-numeric: tabular-nums; }
  .kuku-timer.warn { color: #a14428; }
  .kuku-equation { margin: 30px 0 18px; font-size: clamp(46px, 10vw, 78px); font-weight: 1000; letter-spacing: .02em; }
  .kuku-prompt { min-height: 24px; margin: 0 0 12px; color: #665f56; font-size: 13px; font-weight: 850; }
  .kuku-controls { width: min(520px, 100%); display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin: 0 auto 12px; }
  .kuku-controls button { min-height: 42px; font-size: 12px; }
  .kuku-answer-display { width: min(320px, 100%); min-height: 62px; display: grid; place-items: center; margin: 10px auto; border: 2px solid #cec6b8; border-radius: 14px; background: #fff; font-size: 30px; font-weight: 1000; }
  .kuku-keypad { width: min(430px, 100%); display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin: 10px auto; }
  .kuku-keypad button { min-height: 56px; font-size: 21px; }
  .kuku-feedback { min-height: 34px; margin-top: 10px; font-size: 18px; font-weight: 950; }
  .kuku-feedback.good { color: #2f6a43; }
  .kuku-feedback.bad { color: #a14428; }
  .kuku-actions { display: flex; gap: 8px; justify-content: center; flex-wrap: wrap; margin-top: 14px; }
  .kuku-result-score { margin: 8px 0; font-size: clamp(36px, 7vw, 58px); font-weight: 1000; }
  @media (max-width: 760px) {
    .kuku-level-grid { grid-template-columns: 1fr; }
    .kuku-level-card { min-height: 0; }
    .kuku-game-card { margin-top: 8px; padding: 12px; }
    .kuku-equation { margin: 18px 0 12px; font-size: clamp(44px, 14vw, 62px); }
    .kuku-keypad button { min-height: 48px; }
  }

  /* =====================================================
     MENTAL ARITHMETIC MODE
     ===================================================== */
  .anzan-view,
  .settings-view {
    display: none;
  }

  .anzan-view.show,
  .settings-view.show {
    display: block;
  }

  .anzan-hero,
  .settings-hero {
    padding: 18px;
    border: 1px solid #dcd5c8;
    border-radius: 20px;
    background: #fff;
  }

  .anzan-hero h2,
  .settings-hero h2 {
    margin: 0 0 7px;
    font-size: clamp(24px, 4vw, 34px);
  }

  .anzan-hero p,
  .settings-hero p {
    margin: 0;
    color: #6b655d;
    font-size: 13px;
    line-height: 1.7;
  }

  .anzan-level-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 12px;
    margin-top: 16px;
  }

  .anzan-level-card {
    display: flex;
    flex-direction: column;
    min-height: 190px;
    padding: 16px;
    border: 1px solid #ddd7ca;
    border-radius: 18px;
    background: #fff;
  }

  .anzan-level-no {
    color: #8a8277;
    font-size: 11px;
    font-weight: 950;
    letter-spacing: .08em;
  }

  .anzan-level-name {
    margin: 7px 0;
    font-size: 19px;
    font-weight: 1000;
  }

  .anzan-level-desc {
    flex: 1;
    color: #6d675f;
    font-size: 12px;
    line-height: 1.6;
  }

  .anzan-game-card {
    margin-top: 14px;
    padding: 18px;
    border: 2px solid #ddd7ca;
    border-radius: 22px;
    background: #fff;
    text-align: center;
  }

  .anzan-status {
    display: flex;
    justify-content: space-between;
    gap: 10px;
    color: #6e685f;
    font-size: 12px;
    font-weight: 900;
  }

  .anzan-flash {
    min-height: 160px;
    display: grid;
    place-items: center;
    margin: 16px 0 10px;
    border: 2px solid #e0d8ca;
    border-radius: 20px;
    background: #fffdf8;
    font-size: clamp(54px, 12vw, 92px);
    font-weight: 1000;
    font-variant-numeric: tabular-nums;
  }

  .anzan-flash.ready {
    color: #786f65;
    font-size: clamp(28px, 6vw, 42px);
  }

  .anzan-flash.answer {
    border-color: #9db5c8;
    background: #f4f9fc;
  }

  .anzan-hint {
    min-height: 24px;
    margin-bottom: 10px;
    color: #716a61;
    font-size: 12px;
    font-weight: 800;
  }

  .anzan-answer-display {
    width: min(320px, 100%);
    min-height: 64px;
    display: grid;
    place-items: center;
    margin: 10px auto;
    border: 2px solid #cec6b8;
    border-radius: 14px;
    background: #fff;
    font-size: 30px;
    font-weight: 1000;
  }

  .anzan-keypad {
    width: min(430px, 100%);
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
    margin: 10px auto;
  }

  .anzan-keypad button {
    min-height: 58px;
    font-size: 21px;
  }

  .anzan-feedback {
    min-height: 34px;
    margin-top: 10px;
    font-size: 18px;
    font-weight: 950;
  }

  .anzan-feedback.good {
    color: #2f6a43;
  }

  .anzan-feedback.bad {
    color: #a14428;
  }

  .anzan-result {
    margin-top: 14px;
    padding: 24px 18px;
    border: 2px solid #ddd7ca;
    border-radius: 22px;
    background: #fff;
    text-align: center;
  }

  .anzan-result-score {
    margin: 8px 0;
    font-size: clamp(36px, 7vw, 58px);
    font-weight: 1000;
  }

  .anzan-actions {
    display: flex;
    gap: 8px;
    justify-content: center;
    margin-top: 14px;
  }

  /* =====================================================
     SETTINGS
     ===================================================== */
  .settings-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px;
    margin-top: 16px;
  }

  .setting-card {
    padding: 16px;
    border: 1px solid #ddd7ca;
    border-radius: 18px;
    background: #fff;
  }

  .setting-title {
    margin-bottom: 5px;
    font-size: 16px;
    font-weight: 1000;
  }

  .setting-desc {
    min-height: 38px;
    color: #706960;
    font-size: 12px;
    line-height: 1.55;
  }

  .setting-value {
    margin: 10px 0 7px;
    color: #315f86;
    font-size: 20px;
    font-weight: 1000;
  }

  .setting-card button {
    width: 100%;
  }

  .settings-save-note {
    margin-top: 14px;
    padding: 12px 14px;
    border-radius: 14px;
    background: #f1eee7;
    color: #665f56;
    font-size: 12px;
    line-height: 1.65;
  }

  .subview-topbar {
    position: sticky;
    top: 0;
    z-index: 1000;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin: 0 0 14px;
    padding: 8px 0;
    background: rgba(247,245,239,.96);
    backdrop-filter: blur(6px);
  }

  .subview-topbar-title {
    font-size: 14px;
    font-weight: 950;
    color: #5f5951;
  }

  .top-back-btn {
    position: relative;
    z-index: 1001;
    min-width: 96px;
    min-height: 44px;
    padding: 9px 13px;
    font-size: 13px;
    background: #e8e1d5;
    border: 1px solid #cfc5b7;
    pointer-events: auto !important;
    touch-action: manipulation;
  }

  /* =====================================================
     LEARNING MODE
     ===================================================== */
  .learning-view {
    display: none;
  }

  .learning-view.show {
    display: block;
  }

  .learning-hero {
    padding: 18px 18px 16px;
    border: 1px solid #dcd5c8;
    border-radius: 20px;
    background: #fff;
  }

  .learning-hero h2 {
    margin: 0 0 6px;
    font-size: clamp(24px, 4vw, 34px);
  }

  .learning-hero p {
    margin: 0;
    color: #6b655d;
    line-height: 1.7;
    font-size: 13px;
  }

  .learning-progress-summary {
    margin-top: 12px;
    font-size: 12px;
    font-weight: 850;
    color: #5d574f;
  }

  .learning-progress-track {
    height: 10px;
    margin-top: 7px;
    overflow: hidden;
    border-radius: 999px;
    background: #ebe6dd;
  }

  .learning-progress-bar {
    width: 0%;
    height: 100%;
    border-radius: inherit;
    background: #5d8c62;
    transition: width .3s ease;
  }

  .learning-category-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 14px;
    margin-top: 16px;
  }

  .learning-category-card {
    display: flex;
    flex-direction: column;
    min-height: 208px;
    padding: 18px;
    border: 1px solid #ddd7ca;
    border-radius: 20px;
    background: #fff;
  }

  .learning-category-symbol {
    font-size: 34px;
    font-weight: 1000;
    line-height: 1;
  }

  .learning-category-title {
    margin: 10px 0 5px;
    font-size: 21px;
    font-weight: 1000;
  }

  .learning-category-desc {
    flex: 1;
    color: #6b655d;
    font-size: 13px;
    line-height: 1.6;
  }

  .learning-stars {
    margin: 10px 0;
    font-size: 14px;
    font-weight: 950;
    letter-spacing: .06em;
    color: #7e6c35;
  }

  .learning-stage-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px;
    margin-top: 14px;
  }

  .learning-stage-card {
    position: relative;
    min-height: 154px;
    padding: 16px;
    border: 1px solid #ddd7ca;
    border-radius: 18px;
    background: #fff;
  }

  .learning-stage-card.locked {
    opacity: .53;
    background: #f1eee8;
  }

  .learning-stage-card.cleared {
    border-color: #a8c4a7;
    background: #f7fbf5;
  }

  .learning-stage-no {
    font-size: 11px;
    font-weight: 950;
    letter-spacing: .08em;
    color: #8a8277;
  }

  .learning-stage-title {
    margin: 6px 0 5px;
    font-size: 17px;
    font-weight: 950;
  }

  .learning-stage-desc {
    min-height: 38px;
    color: #6d675f;
    font-size: 12px;
    line-height: 1.55;
  }

  .learning-stage-status {
    margin-top: 8px;
    font-size: 12px;
    font-weight: 900;
  }

  .learning-stage-card button {
    width: 100%;
    margin-top: 10px;
    min-height: 40px;
    padding: 7px 10px;
  }

  .learning-lesson-head {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 12px;
    align-items: center;
    margin: 4px 0 14px;
  }

  .learning-lesson-kicker {
    font-size: 11px;
    font-weight: 950;
    color: #81796f;
    letter-spacing: .08em;
  }

  .learning-lesson-title {
    margin-top: 4px;
    font-size: clamp(22px, 4vw, 30px);
    font-weight: 1000;
  }

  .learning-example-card {
    margin-top: 12px;
    padding: 16px;
    border: 2px solid #d8d0c2;
    border-radius: 20px;
    background: #fffdf8;
    text-align: center;
  }

  .learning-example-label {
    margin-bottom: 6px;
    color: #81796f;
    font-size: 11px;
    font-weight: 950;
    letter-spacing: .08em;
  }

  .learning-example-problem {
    font-size: clamp(34px, 7vw, 58px);
    font-weight: 1000;
    letter-spacing: .04em;
    color: #24231f;
    line-height: 1.25;
  }

  .learning-example-help {
    margin-top: 7px;
    color: #6d675f;
    font-size: 12px;
    line-height: 1.55;
  }

  .learning-video-card,
  .learning-explain-card,
  .learning-quiz-card {
    margin-top: 12px;
    padding: 16px;
    border: 2px solid #ddd7ca;
    border-radius: 20px;
    background: #fff;
  }

  .learning-video-card {
    transition:
      border-color .35s ease,
      box-shadow .35s ease,
      background .35s ease;
  }

  /* スタート前／ループ先頭は通常の枠色。 */
  .learning-video-card.is-active {
    border-color: #8eabc2;
    background: #fbfdff;
    box-shadow: 0 0 0 2px rgba(91, 132, 166, .10);
  }

  /* 答えの珠の形まで到達したら、もう一段階はっきり変える。 */
  .learning-video-card.is-answer {
    border-color: #78a276;
    background: #fbfef9;
    box-shadow: 0 0 0 3px rgba(78, 132, 76, .13);
  }

  .learning-answer-red {
    color: #c9362b;
    font-weight: 1000;
  }

  .learning-video-title {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    margin-bottom: 10px;
    font-size: 15px;
    font-weight: 950;
  }

  .learning-video-badge {
    padding: 5px 8px;
    border-radius: 999px;
    background: #e8f0e2;
    color: #355635;
    font-size: 11px;
    font-weight: 900;
  }

  .learning-step-text {
    min-height: 52px;
    margin: 8px 0 10px;
    text-align: center;
    font-size: 16px;
    line-height: 1.6;
    font-weight: 900;
    color: #4b463f;
  }

  .learning-frame-counter {
    text-align: center;
    font-size: 11px;
    color: #847c72;
  }

  .learning-video-controls {
    display: flex;
    justify-content: center;
    gap: 8px;
    flex-wrap: wrap;
    margin-top: 10px;
  }

  .learning-video-controls button {
    min-height: 38px;
    padding: 7px 11px;
    font-size: 12px;
  }

  .learning-voice-btn {
    border: 1px solid #d1cabd;
    background: #eee9df;
  }

  .learning-voice-btn.on {
    border-color: #a9cfb3;
    background: #dff1e3;
    color: #285a36;
  }

  .learning-voice-note {
    min-height: 22px;
    margin-top: 7px;
    text-align: center;
    color: #756e65;
    font-size: 11px;
    font-weight: 750;
  }

  .learning-soroban-wrap {
    overflow-x: auto;
    padding: 4px 2px 8px;
  }

  .learning-soroban-board {
    --rod-width: 64px;
    position: relative;
    display: flex;
    justify-content: center;
    align-items: flex-start;
    gap: 5px;
    min-width: max-content;
    padding: 12px 14px 8px;
    border: 5px solid #73543a;
    border-radius: 14px;
    background: #e8c895;
    box-shadow:
      inset 0 0 0 2px rgba(255,255,255,.35),
      0 6px 15px rgba(72, 54, 37, .12);
  }

  .learning-soroban-board::before {
    content: "";
    position: absolute;
    left: 7px;
    right: 7px;
    top: 78px;
    height: 8px;
    border-radius: 5px;
    background: #66452f;
    z-index: 3;
  }

  .learning-point-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }

  .learning-point {
    padding: 12px;
    border-radius: 14px;
    background: #f7f4ee;
  }

  .learning-point.trouble {
    background: #fff6df;
  }

  .learning-point-label {
    margin-bottom: 5px;
    font-size: 12px;
    font-weight: 950;
  }

  .learning-point-text {
    color: #5f5951;
    font-size: 13px;
    line-height: 1.65;
  }

  .learning-rule-box {
    margin-top: 10px;
    padding: 12px 14px;
    border-left: 5px solid #6f936c;
    border-radius: 10px;
    background: #f3f8f1;
    font-size: 14px;
    font-weight: 900;
    line-height: 1.65;
  }

  .learning-quiz-question {
    margin-bottom: 10px;
    font-size: 16px;
    font-weight: 950;
    line-height: 1.55;
  }

  .learning-quiz-options {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 8px;
  }

  .learning-quiz-option {
    min-height: 54px;
    font-size: 16px;
  }

  .learning-quiz-option.correct-choice {
    background: #dff1e3;
    color: #285a36;
  }

  .learning-quiz-option.wrong-choice {
    background: #f4ded8;
    color: #8a3d28;
  }

  .learning-quiz-feedback {
    min-height: 34px;
    margin-top: 10px;
    text-align: center;
    font-size: 15px;
    font-weight: 950;
  }

  .learning-clear-actions {
    display: none;
    gap: 8px;
    margin-top: 10px;
  }

  .learning-clear-actions.show {
    display: flex;
  }

  .learning-clear-actions button {
    flex: 1;
  }

  @media (max-width: 640px) {
    .home-mode-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
    }

    .home-mode-btn {
      min-height: 148px;
      padding: 14px 10px;
    }

    .home-mode-name {
      font-size: 20px;
    }

    .home-mode-desc {
      font-size: 11px;
    }

    .home-weakness-btn {
      min-height: 84px;
      padding: 12px 13px;
    }

    .challenge-operation-nav {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .rank-goal-row {
      grid-template-columns: 62px minmax(0, 1fr);
    }

    .rank-goal-status {
      grid-column: 2;
      justify-self: start;
    }

    .learning-category-grid,
    .learning-stage-grid,
    .learning-point-grid,
    .anzan-level-grid,
    .settings-grid {
      grid-template-columns: 1fr;
    }

    .learning-quiz-options {
      grid-template-columns: 1fr;
    }
  }

  .intro {
    display: flex;
    justify-content: space-between;
    align-items: end;
    gap: 16px;
    margin-bottom: 18px;
  }

  .lead {
    max-width: 820px;
    font-size: 14px;
    line-height: 1.7;
    color: #66635d;
  }

  .time-limit-control {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 10px;
    flex-wrap: wrap;
    margin: 10px 0 20px;
  }

  .time-limit-label {
    color: #66635d;
    font-size: 13px;
    font-weight: 850;
  }

  .time-limit-toggle {
    min-height: 42px;
    padding: 8px 14px;
    border-radius: 999px;
    border: 1px solid #cfc7b9;
    background: #fff;
    color: #2e2b27;
    font-size: 13px;
    font-weight: 900;
  }

  .time-limit-toggle.off {
    background: #ece8df;
    color: #56504a;
  }

  .badge {
    white-space: nowrap;
    border: 1px solid #d8d2c6;
    border-radius: 999px;
    padding: 8px 12px;
    font-size: 13px;
    font-weight: 850;
  }

  .level-title {
    margin: 22px 0 10px;
    font-size: 20px;
    font-weight: 900;
  }

  .mode-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 12px;
  }

  .mode-card {
    display: flex;
    flex-direction: column;
    min-height: 180px;
    padding: 16px;
    border: 1px solid #ddd7ca;
    border-radius: 18px;
    background: #fff;
  }

  .mode-card.rank-recommended {
    border: 2px solid #c89a3d;
    background: #fffaf0;
    box-shadow: 0 0 0 3px rgba(200, 154, 61, .10);
  }

  .rank-recommend-chip {
    background: #f5dfae !important;
    color: #6d501c;
  }

  .next-rank-guide,
  .challenge-resume-card,
  .weakness-challenge-note {
    margin: 12px 0 16px;
    padding: 14px 16px;
    border: 1px solid #d9d1c4;
    border-radius: 16px;
    background: #fffdf8;
  }

  .next-rank-guide {
    border-width: 2px;
    border-color: #d6b66d;
    background: #fffaf0;
  }

  .next-rank-guide-title,
  .challenge-resume-title {
    font-size: 15px;
    font-weight: 1000;
    color: #4c463d;
  }

  .next-rank-guide-text,
  .challenge-resume-text,
  .weakness-challenge-note {
    margin-top: 5px;
    font-size: 11px;
    line-height: 1.6;
    color: #6d665d;
  }

  .challenge-resume-actions {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 8px;
    margin-top: 10px;
  }

  .challenge-resume-actions button {
    min-height: 40px;
  }

  .weakness-mode-card .mode-desc {
    min-height: 42px;
  }

  .weakness-empty {
    grid-column: 1 / -1;
    padding: 16px;
    border: 1px dashed #d4ccbf;
    border-radius: 14px;
    background: #faf8f4;
    color: #7c746a;
    text-align: center;
    font-size: 12px;
    line-height: 1.6;
  }

  .mode-no {
    font-size: 12px;
    font-weight: 900;
    letter-spacing: .08em;
    color: #817b70;
  }

  .mode-name {
    margin: 6px 0 8px;
    font-size: 18px;
    font-weight: 900;
  }

  .mode-desc {
    flex: 1;
    font-size: 13px;
    line-height: 1.6;
    color: #66635d;
  }

  .chips {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    margin: 10px 0;
  }

  .chip {
    padding: 5px 8px;
    border-radius: 999px;
    background: #f2eee5;
    font-size: 12px;
    font-weight: 800;
  }

  .hidden { display: none !important; }
  .workspace { display: none; }
  .workspace.show { display: block; }

  .statusbar {
    position: sticky;
    top: 0;
    z-index: 35;
    display: grid;
    grid-template-columns: minmax(200px, 1fr) auto auto auto auto auto auto;
    align-items: center;
    gap: 12px;
    padding: 14px 16px;
    border: 1px solid #ddd7ca;
    border-radius: 18px;
    background: #fff;
  }

  .status-title {
    font-size: 16px;
    font-weight: 900;
  }

  .status-sub {
    margin-top: 3px;
    font-size: 12px;
    color: #706c64;
  }

  .timer {
    min-width: 88px;
    text-align: center;
    font-size: 25px;
    font-weight: 950;
    font-variant-numeric: tabular-nums;
  }

  .timer.warn { color: #a14428; }

  .streak {
    white-space: nowrap;
    font-size: 14px;
    font-weight: 900;
  }

  .voice-btn.on {
    background: #dff1e3;
    color: #285a36;
    border: 1px solid #a9cfb3;
  }

  .challenge-quick-nav {
    grid-column: 1 / -1;
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 8px;
  }

  .challenge-quick-nav button {
    min-height: 40px;
    font-size: 12px;
  }

  .voice-status {
    grid-column: 1 / -1;
    font-size: 12px;
    color: #706c64;
  }

  .voice-status.listening {
    color: #2f6a43;
    font-weight: 900;
  }

  .bgm-name {
    grid-column: 1 / -1;
    font-size: 12px;
    color: #706c64;
  }

  .question-card.voice-waiting .qtop,
  .question-card.voice-waiting .equation,
  .question-card.voice-waiting .hint-launch,
  .question-card.voice-waiting .abacus-hint,
  .question-card.voice-waiting .answer-form,
  .question-card.voice-waiting .keypad,
  .question-card.voice-waiting .feedback {
    visibility: hidden !important;
  }

  .question-card.voice-waiting::after {
    content: "ご破算！";
    position: absolute;
    inset: 0;
    display: grid;
    place-items: center;
    font-size: clamp(34px, 7vw, 64px);
    font-weight: 1000;
    letter-spacing: .08em;
    color: #5c5144;
    pointer-events: none;
  }

  .question-card {
    position: relative;
    min-height: 560px;
    margin-top: 14px;
    padding: 24px;
    border: 2px solid #ddd7ca;
    border-radius: 22px;
    background: #fff;
    transition:
      border-color .25s ease,
      border-width .25s ease,
      box-shadow .25s ease,
      background .25s ease,
      transform .25s ease;
  }

  .question-card.streak6,
  .kuku-game-card.streak6,
  .question-card.streak10 ,
  .kuku-game-card.streak10 {
    border: 7px solid transparent !important;
    background:
      linear-gradient(#fffdf9, #fffdf9) padding-box,
      linear-gradient(
        90deg,
        var(--rb1, #ff3b30),
        var(--rb2, #ff9500),
        var(--rb3, #ffd60a),
        var(--rb4, #34c759),
        var(--rb5, #0a84ff),
        var(--rb6, #5e5ce6),
        var(--rb7, #bf5af2),
        var(--rb8, #ff3b30)
      ) border-box !important;
    background-size: 100% 100%, 300% 100% !important;
    animation: rainbowBorder 2.2s linear infinite;
  }

  .question-card.streak6 ,
  .kuku-game-card.streak6 {
    box-shadow: none !important;
  }

  .question-card.streak10 ,
  .kuku-game-card.streak10 {
    box-shadow: none;
  }

  /* 10問連続正解以上：
     レインボー枠は常時、発光は新しい問題が出た瞬間だけ。 */
  .question-card.streak10.question-flash ,
  .kuku-game-card.streak10.question-flash {
    animation:
      rainbowBorder 2.2s linear infinite;
  }

  .question-card.streak10.question-flash::before ,
  .kuku-game-card.streak10.question-flash::before {
    content: "";
    position: absolute;
    inset: -14px;
    border-radius: 32px;
    pointer-events: none;
    z-index: 20;
    opacity: 0;
    border: 6px solid rgba(255,255,255,.94);
    box-shadow:
      0 0 18px 7px rgba(255, 214, 10, .75),
      0 0 38px 15px rgba(255, 59, 48, .58),
      0 0 62px 22px rgba(10, 132, 255, .46),
      inset 0 0 22px rgba(191, 90, 242, .42);
    animation:
      questionFlashHalo 1.15s cubic-bezier(.16,.8,.25,1);
  }

  @keyframes rainbowBorder {
    from { background-position: 0 0, 0% 50%; }
    to   { background-position: 0 0, 300% 50%; }
  }

  @keyframes questionFlashHalo {
    0% {
      opacity: 0;
      transform: scale(.975);
    }
    16% {
      opacity: 1;
      transform: scale(1.015);
    }
    42% {
      opacity: .95;
      transform: scale(1.025);
    }
    100% {
      opacity: 0;
      transform: scale(1.045);
    }
  }

  .qtop {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
  }

  .qcount, .score {
    font-size: 13px;
    font-weight: 850;
  }

  .qcount { color: #706c64; }

  .weak-badge {
    display: none;
    margin-left: 8px;
    padding: 5px 9px;
    border-radius: 999px;
    background: #fff1c9;
    color: #805b00;
    font-size: 12px;
    font-weight: 900;
  }

  .weak-badge.show {
    display: inline-block;
  }

  .equation {
    margin: 38px 0 22px;
    text-align: center;
    font-size: clamp(42px, 7vw, 68px);
    font-weight: 950;
    letter-spacing: .03em;
  }

  .equation.multi-term {
    font-size: clamp(28px, 5vw, 48px);
    line-height: 1.18;
    overflow-wrap: anywhere;
  }

  .equation.multi-term.long-sequence {
    font-size: clamp(22px, 4vw, 38px);
  }

  .hint-launch {
    display: flex;
    justify-content: center;
    margin: -4px 0 14px;
  }

  .hint-btn {
    background: #e8f0e2;
    color: #345233;
    border: 1px solid #c9d8c0;
  }

  .abacus-hint {
    display: none;
    width: min(760px, 100%);
    margin: 0 auto 18px;
    padding: 14px;
    border: 2px solid #d7c69e;
    border-radius: 18px;
    background: #fffaf0;
  }

  .abacus-hint.show {
    display: block;
    animation: hintOpen .22s ease-out;
  }

  @keyframes hintOpen {
    from {
      opacity: 0;
      transform: translateY(-6px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  .hint-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 10px;
    margin-bottom: 8px;
  }

  .hint-title {
    font-size: 15px;
    font-weight: 950;
  }

  .hint-manual-nav {
    display: grid;
    grid-template-columns: 1fr auto 1fr;
    align-items: center;
    gap: 8px;
    margin: 12px 0 8px;
  }

  .hint-manual-nav button {
    min-height: 46px;
    font-size: 14px;
    font-weight: 950;
  }

  .hint-manual-counter {
    min-width: 68px;
    text-align: center;
    color: #6d665d;
    font-size: 12px;
    font-weight: 950;
  }

  .hint-manual-nav button:disabled {
    opacity: .35;
    cursor: default;
  }

  .hint-lower-panel {
    padding-top: 4px;
  }

  .hint-step {
    min-height: 34px;
    margin: 5px 0 7px;
    text-align: center;
    font-size: 15px;
    font-weight: 900;
    line-height: 1.42;
    color: #4c473e;
    white-space: pre-line;
  }

  .hint-voice-status {
    display: none;
    width: min(560px, 100%);
    margin: 0 auto 6px;
    padding: 7px 10px;
    border: 1px solid #d7cfbf;
    border-radius: 12px;
    background: #f6f1e8;
    color: #5f584e;
    text-align: center;
    font-size: 12px;
    font-weight: 900;
    line-height: 1.5;
  }

  .hint-voice-status.show {
    display: block;
  }

  .hint-voice-status.listening {
    border-color: #9cbca7;
    background: #e9f4ec;
    color: #315f40;
  }

  .hint-voice-status.correct {
    border-color: #d4b95d;
    background: #fff7d8;
    color: #6d5715;
  }

  .hint-voice-status.wrong {
    border-color: #d5aaa0;
    background: #fff0ec;
    color: #7a3b2e;
  }

  .hint-answer-controls {
    display: none;
    width: min(560px, 100%);
    margin: 0 auto 6px;
  }

  .hint-answer-controls.show {
    display: block;
  }

  .hint-mic-answer-btn {
    width: 100%;
    min-height: 44px;
    margin-bottom: 8px;
    border-color: #9cbca7;
    background: #e9f4ec;
    color: #315f40;
    font-weight: 950;
  }

  .hint-mic-answer-btn.listening {
    background: #d8ecde;
    border-color: #6f9e7d;
  }

  .hint-number-grid {
    display: grid;
    grid-template-columns: repeat(9, minmax(0, 1fr));
    gap: 5px;
  }

  .hint-number-btn {
    min-height: 38px;
    padding: 5px 2px;
    font-size: 15px;
    font-weight: 950;
  }

  @media (max-width: 640px) {
    .hint-number-grid {
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 6px;
    }

    .hint-number-btn {
      min-height: 42px;
    }
  }

  .hint-actions {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
  }

  .hint-actions button {
    min-height: 36px;
    padding: 7px 10px;
    font-size: 12px;
  }

  .soroban-scroll {
    overflow-x: auto;
    padding: 2px 2px 4px;
    margin: 0;
  }

  .soroban-board {
    --rod-width: 64px;
    position: relative;
    display: flex;
    justify-content: center;
    align-items: flex-start;
    gap: 5px;
    min-width: max-content;
    padding: 12px 14px 8px;
    border: 5px solid #73543a;
    border-radius: 14px;
    background: #e8c895;
    box-shadow:
      inset 0 0 0 2px rgba(255,255,255,.35),
      0 6px 15px rgba(72, 54, 37, .12);
  }

  .soroban-board::before {
    content: "";
    position: absolute;
    left: 7px;
    right: 7px;
    top: 78px;
    height: 8px;
    border-radius: 5px;
    background: #66452f;
    z-index: 3;
  }

  .soroban-rod {
    position: relative;
    width: var(--rod-width);
    height: 202px;
    border-radius: 12px;
    transition:
      background .25s ease,
      box-shadow .25s ease;
  }

  .soroban-rod.active {
    background: rgba(255, 238, 155, .58);
    box-shadow:
      inset 0 0 0 2px rgba(236, 175, 37, .78),
      0 0 16px rgba(236, 175, 37, .38);
  }

  .rod-line {
    position: absolute;
    left: 50%;
    top: 5px;
    bottom: 30px;
    width: 3px;
    transform: translateX(-50%);
    border-radius: 2px;
    background: #6b4b33;
    z-index: 1;
  }

  .soroban-bead {
    position: absolute;
    left: 50%;
    width: 48px;
    height: 16px;
    transform: translateX(-50%);
    border: 2px solid #8d4929;
    border-radius: 50% 50% 44% 44%;
    background:
      linear-gradient(
        180deg,
        #ef9b5c 0%,
        #c86735 54%,
        #a84d27 100%
      );
    box-shadow:
      inset 0 2px 2px rgba(255,255,255,.38),
      0 2px 3px rgba(77,40,21,.24);
    z-index: 4;
    transition:
      top .58s cubic-bezier(.22,.8,.24,1),
      filter .22s ease,
      transform .22s ease;
  }

  .soroban-rod.active .soroban-bead {
    filter: saturate(1.08) brightness(1.04);
  }

  .soroban-bead.used-glow {
    border-color: #d2bd69;
    background:
      linear-gradient(
        180deg,
        #fff9d8 0%,
        #f8ecad 54%,
        #e8d790 100%
      );
    box-shadow:
      0 0 8px rgba(255, 235, 150, .58),
      0 0 17px rgba(255, 226, 112, .28),
      inset 0 1px 1px rgba(255,255,255,.68);
    filter: brightness(1.04) saturate(.70);
  }

  .soroban-board.slow-hint-motion .soroban-bead {
    transition:
      top 1.35s cubic-bezier(.22,.8,.24,1),
      filter .35s ease,
      background .35s ease,
      box-shadow .35s ease,
      transform .35s ease;
  }

  .upper-bead {
    top: 13px;
  }

  .lower-bead {
    top: 112px;
  }

  .rod-place {
    position: absolute;
    left: 0;
    right: 0;
    bottom: 5px;
    text-align: center;
    font-size: 12px;
    font-weight: 950;
    color: #604a39;
  }

  .hint-legend {
    margin-top: 4px;
    text-align: center;
    font-size: 11px;
    line-height: 1.5;
    color: #71695f;
  }

  .answer-form {
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }

  .answer-input {
    width: min(280px, 100%);
    min-height: 62px;
    padding: 8px 12px;
    border: 2px solid #c8c1b4;
    border-radius: 14px;
    background: #fff;
    color: #24231f;
    text-align: center;
    font-size: 30px;
    font-weight: 900;
  }

  .keypad-wrap {
    width: min(360px, 100%);
    margin: 16px auto 0;
  }

  .keypad-label {
    margin-bottom: 8px;
    text-align: center;
    font-size: 13px;
    font-weight: 850;
    color: #706c64;
  }

  .keypad {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 9px;
  }

  .keypad button {
    min-height: 62px;
    border: 1px solid #d4cec1;
    background: #f3efe7;
    color: #24231f;
    font-size: 24px;
    font-weight: 900;
    user-select: none;
  }

  .keypad button:active {
    transform: translateY(1px);
    background: #e7e0d4;
  }

  .keypad .key-action {
    background: #e5e0d6;
    font-size: 14px;
  }

  .feedback {
    min-height: 36px;
    margin-top: 14px;
    text-align: center;
    font-size: 20px;
    font-weight: 900;
  }

  .feedback.good { color: #28704a; }
  .feedback.bad { color: #a14428; }

  .progress {
    height: 8px;
    margin-top: 18px;
    overflow: hidden;
    border-radius: 999px;
    background: #e7e2d9;
  }

  .bar {
    width: 0;
    height: 100%;
    background: #6d815d;
    transition: width .25s ease;
  }

  .results {
    display: none;
    margin-top: 14px;
    padding: 24px;
    border: 1px solid #ddd7ca;
    border-radius: 22px;
    background: #fff;
  }

  .results.show { display: block; }

  .score-stage {
    position: relative;
    overflow: hidden;
    margin: 10px auto 14px;
    padding: 22px 12px 18px;
    border: 2px solid #e1d6bf;
    border-radius: 22px;
    background:
      radial-gradient(circle at 50% 20%, #fff8d4 0, #fff 56%);
    text-align: center;
  }

  .score-caption {
    margin-bottom: 4px;
    font-size: 14px;
    font-weight: 900;
    color: #74654e;
  }

  .result-score {
    min-height: 74px;
    margin: 6px 0;
    text-align: center;
    font-size: clamp(54px, 10vw, 88px);
    line-height: 1;
    font-weight: 1000;
    letter-spacing: .02em;
    font-variant-numeric: tabular-nums;
    transform-origin: center;
  }

  .result-score.roulette {
    animation: scoreRoulette .16s linear infinite;
    filter: blur(.35px);
  }

  .result-score.reveal {
    animation: scoreReveal .85s cubic-bezier(.18,.9,.2,1.25);
    text-shadow:
      0 3px 0 rgba(255,255,255,.9),
      0 0 18px rgba(255, 189, 35, .55),
      0 0 34px rgba(255, 96, 52, .34);
  }

  @keyframes scoreRoulette {
    0%   { transform: perspective(500px) rotateX(0deg) scale(1); }
    50%  { transform: perspective(500px) rotateX(90deg) scale(1.04); }
    100% { transform: perspective(500px) rotateX(180deg) scale(1); }
  }

  @keyframes scoreReveal {
    0%   { transform: scale(.35) rotate(-7deg); opacity: .2; }
    55%  { transform: scale(1.32) rotate(3deg); opacity: 1; }
    75%  { transform: scale(.94) rotate(-1deg); }
    100% { transform: scale(1) rotate(0); }
  }

  .score-formula {
    min-height: 44px;
    margin-top: 8px;
    font-size: 13px;
    line-height: 1.65;
    color: #685f55;
  }

  .score-stage.score-rainbow {
    border: 7px solid transparent;
    background:
      radial-gradient(circle at 50% 20%, #fff8d4 0, #fff 56%) padding-box,
      linear-gradient(
        90deg,
        #ff3b30,
        #ff9500,
        #ffd60a,
        #34c759,
        #0a84ff,
        #5e5ce6,
        #bf5af2,
        #ff3b30
      ) border-box;
    background-size: 100% 100%, 300% 100%;
    animation: scoreRainbow 2s linear infinite;
  }

  .score-stage.babaan {
    animation: scoreStageBang .72s ease-out;
  }

  .score-stage.score-rainbow.babaan {
    animation:
      scoreStageBang .72s ease-out,
      scoreRainbow 2s linear infinite;
  }

  @keyframes scoreRainbow {
    from { background-position: 0 0, 0% 50%; }
    to   { background-position: 0 0, 300% 50%; }
  }

  @keyframes scoreStageBang {
    0%   { transform: scale(1); }
    24%  { transform: scale(1.035); }
    45%  { transform: scale(.985); }
    100% { transform: scale(1); }
  }

  .confetti-piece {
    position: absolute;
    top: -16px;
    width: 9px;
    height: 16px;
    border-radius: 2px;
    pointer-events: none;
    z-index: 8;
    animation: confettiFall 1.8s ease-in forwards;
  }

  @keyframes confettiFall {
    0% {
      transform: translate3d(0, -10px, 0) rotate(0deg);
      opacity: 1;
    }
    100% {
      transform: translate3d(var(--drift), 240px, 0) rotate(var(--spin));
      opacity: 0;
    }
  }

  .result-note {
    text-align: center;
    color: #66635d;
    line-height: 1.7;
  }

  .ranking-panel {
    margin: 18px auto;
    padding: 14px;
    border: 1px solid #ddd7ca;
    border-radius: 16px;
    background: #fbfaf7;
  }

  .ranking-panel-title {
    margin-bottom: 8px;
    font-size: 14px;
    font-weight: 950;
    color: #554d43;
  }

  .ranking-note {
    margin-bottom: 8px;
    font-size: 10px;
    line-height: 1.5;
    color: #857d73;
  }

  .ranking-list {
    display: grid;
    gap: 5px;
    max-height: 330px;
    overflow-y: auto;
    padding-right: 2px;
  }

  .ranking-empty {
    padding: 12px 6px;
    text-align: center;
    font-size: 11px;
    color: #928b82;
  }

  .ranking-row {
    display: grid;
    grid-template-columns: 25px minmax(0, 1fr) auto;
    align-items: center;
    gap: 7px;
    padding: 7px 8px;
    border: 1px solid #e7e1d7;
    border-radius: 10px;
    background: #fff;
  }

  .ranking-place {
    text-align: center;
    font-size: 10px;
    font-weight: 900;
    color: #8b8174;
  }

  .ranking-main {
    min-width: 0;
  }

  /* ランキング内の点数は意図的に小さく表示 */
  .ranking-score {
    font-size: 17px;
    line-height: 1.15;
    font-weight: 950;
    font-variant-numeric: tabular-nums;
    color: #463f37;
  }

  .ranking-detail {
    margin-top: 2px;
    font-size: 9px;
    line-height: 1.45;
    color: #91887d;
  }

  .ranking-delete {
    min-height: 28px !important;
    padding: 4px 7px !important;
    font-size: 9px !important;
    color: #765d59;
    background: #fff;
    border: 1px solid #d9c9c6;
  }

  .mode-challenge-count {
    margin: 8px 0 5px;
    text-align: right;
    font-size: 10px;
    font-weight: 800;
    color: #8b8378;
  }

  .ranking-open-btn {
    width: 100%;
    margin-top: 7px;
    min-height: 34px;
    padding: 6px 10px;
    font-size: 11px;
    color: #62594f;
    background: #f7f4ee;
    border: 1px solid #ddd5c8;
  }

  .analysis-control {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 14px;
    margin: 10px 0 18px;
    padding: 14px 16px;
    border: 1px solid #d9d1c4;
    border-radius: 16px;
    background: #fffdf8;
  }

  .analysis-control-title {
    font-size: 14px;
    font-weight: 950;
  }

  .analysis-control-note {
    margin-top: 3px;
    color: #706960;
    font-size: 11px;
    line-height: 1.55;
  }

  .analysis-toggle.on {
    background: #dff1e3;
    color: #285a36;
    border-color: #a9cfb3;
  }

  .recording-badge {
    display: none;
    align-items: center;
    justify-content: center;
    min-height: 34px;
    padding: 6px 10px;
    border-radius: 999px;
    background: #f7dfda;
    color: #9b3524;
    font-size: 11px;
    font-weight: 1000;
    white-space: nowrap;
  }

  .recording-badge.show {
    display: inline-flex;
  }

  .mode-card.camera-setup-active > .start-mode {
    display: none;
  }

  .mode-card.camera-setup-active {
    border-color: #b9c9d5;
  }

  .camera-modal {
    display: none;
    position: static;
    width: 100%;
    margin-top: 12px;
    padding: 0;
    background: transparent;
  }

  .camera-modal.show {
    display: block;
  }

  .camera-dialog {
    width: 100%;
    max-height: none;
    overflow: visible;
    padding: 14px;
    border: 2px solid #d8d0c3;
    border-radius: 18px;
    background: #fffdf8;
    box-shadow: 0 8px 22px rgba(0,0,0,.10);
  }

  .camera-dialog h3 {
    margin: 0 0 6px;
    font-size: 20px;
  }

  .camera-dialog p {
    margin: 0 0 12px;
    color: #675f56;
    font-size: 12px;
    line-height: 1.65;
  }

  .camera-preview-wrap {
    position: relative;
    width: min(100%, 420px);
    aspect-ratio: 4 / 3;
    margin: 0 auto;
    overflow: hidden;
    border-radius: 14px;
    background: #171717;
  }

  .camera-preview {
    display: block;
    width: 100%;
    height: 100%;
    object-fit: cover;
    object-position: center 62%;
    background: #171717;
    transform: scaleX(-1);
  }

  .camera-guide {
    position: absolute;
    left: 5%;
    right: 5%;
    bottom: 5%;
    height: 50%;
    border: 3px dashed rgba(255,255,255,.92);
    border-radius: 16px;
    background: rgba(255,255,255,.04);
    pointer-events: none;
  }

  .camera-guide-label {
    position: absolute;
    left: 50%;
    bottom: 8px;
    transform: translateX(-50%);
    padding: 5px 8px;
    border-radius: 999px;
    background: rgba(0,0,0,.66);
    color: #fff;
    font-size: 10px;
    font-weight: 900;
    white-space: nowrap;
  }

  .camera-face-guide {
    position: absolute;
    left: 50%;
    top: 7%;
    transform: translateX(-50%);
    width: 28%;
    height: 28%;
    border: 2px dashed rgba(255,255,255,.52);
    border-radius: 48%;
    pointer-events: none;
  }

  .camera-face-label {
    position: absolute;
    left: 50%;
    top: 7px;
    transform: translateX(-50%);
    padding: 4px 7px;
    border-radius: 999px;
    background: rgba(0,0,0,.52);
    color: #fff;
    font-size: 9px;
    font-weight: 850;
    white-space: nowrap;
  }

  .camera-status {
    margin-top: 10px;
    padding: 10px 12px;
    border-radius: 12px;
    background: #f2eee6;
    color: #5f594f;
    font-size: 12px;
    line-height: 1.6;
  }

  .camera-actions {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin-top: 10px;
  }

  .camera-actions button {
    min-height: 42px;
    font-size: 12px;
    font-weight: 950;
  }

  .camera-actions #cameraBeginBtn {
    grid-column: 1 / -1;
    min-height: 48px;
    font-size: 14px;
  }

  .coaching-rank-strip {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-top: 12px;
    padding: 12px 14px;
    border-radius: 14px;
    background: #ece7dc;
  }

  .coaching-rank-label {
    color: #6e665d;
    font-size: 11px;
    font-weight: 850;
  }

  .coaching-rank-title {
    margin-top: 2px;
    font-size: 24px;
    font-weight: 1000;
  }

  .coaching-issues {
    display: grid;
    gap: 10px;
    margin-top: 12px;
  }

  .coaching-issue-card {
    padding: 13px;
    border: 1px solid #d8d0c3;
    border-radius: 15px;
    background: #fff;
  }

  .coaching-issue-title {
    font-size: 16px;
    font-weight: 1000;
  }

  .coaching-issue-evidence {
    margin-top: 4px;
    color: #746c62;
    font-size: 11px;
    line-height: 1.55;
  }

  .coaching-issue-explain {
    margin-top: 8px;
    padding: 10px 11px;
    border-radius: 11px;
    background: #f2eee6;
    color: #514b44;
    font-size: 12px;
    line-height: 1.65;
  }

  .coaching-issue-actions {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin-top: 9px;
  }

  .coaching-issue-actions button {
    min-height: 44px;
    font-size: 12px;
    font-weight: 950;
  }

  .app-rank-card {
    margin-top: 16px;
    padding: 16px;
    border: 1px solid #d8d0c3;
    border-radius: 18px;
    background: #fffdf8;
  }

  .app-rank-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 10px;
  }

  .app-rank-title {
    font-size: 15px;
    font-weight: 1000;
  }

  .app-rank-badge {
    padding: 7px 11px;
    border-radius: 999px;
    background: #e8dfc5;
    color: #614f1f;
    font-size: 16px;
    font-weight: 1000;
  }

  .app-rank-meter {
    height: 10px;
    margin-top: 12px;
    overflow: hidden;
    border-radius: 999px;
    background: #e7e1d7;
  }

  .app-rank-meter-fill {
    width: 0;
    height: 100%;
    border-radius: inherit;
    background: #7d8c72;
    transition: width .25s ease;
  }

  .app-rank-note,
  .app-rank-next {
    margin-top: 8px;
    color: #6c655c;
    font-size: 11px;
    line-height: 1.6;
  }


  .medal-collection {
    margin-top: 16px;
    padding: 16px;
    border: 1px solid #d8d0c3;
    border-radius: 18px;
    background: #fffdf8;
  }

  .medal-collection-title {
    font-size: 17px;
    font-weight: 1000;
  }

  .medal-collection-note {
    margin-top: 4px;
    color: #71695f;
    font-size: 11px;
    line-height: 1.6;
  }

  .medal-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 10px;
    margin-top: 14px;
  }

  .medal-slot {
    min-height: 122px;
    display: grid;
    place-items: center;
    align-content: center;
    gap: 8px;
    padding: 10px 6px;
    border: 1px solid #ded7cb;
    border-radius: 15px;
    background: #fff;
    text-align: center;
  }

  .medal-slot.locked {
    background: #f4f1ec;
    color: #9c958b;
  }

  .medal-slot.locked .rank-medal {
    filter: grayscale(1);
    opacity: .22;
  }

  .medal-slot.earned {
    box-shadow: 0 7px 18px rgba(95, 75, 40, .09);
  }

  .medal-slot-name {
    font-size: 11px;
    font-weight: 950;
  }

  .medal-slot-status {
    min-height: 14px;
    color: #837a6d;
    font-size: 9px;
    line-height: 1.35;
  }

  .medal-conditions {
    margin-top: 14px;
    border: 1px solid #ded7cb;
    border-radius: 14px;
    background: #fff;
    overflow: hidden;
  }

  .medal-conditions summary {
    cursor: pointer;
    padding: 12px 14px;
    font-size: 13px;
    font-weight: 950;
    list-style: none;
  }

  .medal-conditions summary::-webkit-details-marker {
    display: none;
  }

  .medal-conditions summary::after {
    content: "＋";
    float: right;
    color: #776e62;
  }

  .medal-conditions[open] summary::after {
    content: "－";
  }

  .medal-condition-list {
    display: grid;
    gap: 7px;
    padding: 0 12px 12px;
  }

  .medal-condition-row {
    display: grid;
    grid-template-columns: 58px 1fr auto;
    gap: 9px;
    align-items: center;
    padding: 9px 10px;
    border-radius: 11px;
    background: #f8f5ef;
  }

  .medal-condition-rank {
    font-size: 12px;
    font-weight: 1000;
  }

  .medal-condition-text {
    color: #665f56;
    font-size: 10px;
    line-height: 1.45;
  }

  .medal-condition-status {
    white-space: nowrap;
    font-size: 9px;
    font-weight: 950;
    color: #7c7469;
  }

  .medal-condition-row.earned .medal-condition-status {
    color: #496c4d;
  }

  .medal-track-heading {
    grid-column: 1 / -1;
    margin-top: 8px;
    padding: 8px 10px;
    border-radius: 10px;
    background: #eee8dc;
    font-size: 13px;
    font-weight: 1000;
  }

  .rank-track-goal-section {
    margin-top: 10px;
    padding: 10px;
    border: 1px solid #ded7cb;
    border-radius: 13px;
    background: #fff;
  }

  .rank-track-goal-title {
    margin-bottom: 5px;
    font-size: 13px;
    font-weight: 1000;
  }

  .medal-reset-box {
    margin-top: 14px;
    padding: 12px;
    border: 1px solid #dfd5c8;
    border-radius: 14px;
    background: #faf7f2;
  }

  .medal-reset-title {
    font-size: 12px;
    font-weight: 1000;
  }

  .medal-reset-note {
    margin-top: 4px;
    color: #756c61;
    font-size: 10px;
    line-height: 1.55;
  }

  .medal-reset-btn {
    width: 100%;
    margin-top: 9px;
    min-height: 42px;
    border-color: #c9a9a0;
    background: #fff8f5;
    color: #74483d;
    font-weight: 950;
  }

  .medal-reset-btn.armed {
    border-color: #b87564;
    background: #f8e5df;
    color: #71382b;
  }

  .medal-reset-status {
    min-height: 16px;
    margin-top: 6px;
    color: #756c61;
    font-size: 10px;
    line-height: 1.45;
  }

  .rank-celebration {
    display: none;
    pointer-events: none;
    position: absolute;
    inset: 0;
    min-height: 100%;
    z-index: 5000;
    align-items: flex-start;
    justify-content: center;
    overflow-x: hidden;
    overflow-y: auto;
    -webkit-overflow-scrolling: touch;
    padding: 16px 18px 24px;
    background:
      radial-gradient(circle at top center, rgba(43,58,83,.38), rgba(15,17,24,.88));
  }

  .rank-celebration.show {
    display: flex;
    pointer-events: auto;
    animation: rankOverlayIn .35s ease both;
  }

  .rank-celebration-card {
    position: relative;
    z-index: 3;
    width: min(430px, 94vw);
    max-width: 430px;
    max-height: none;
    overflow: visible;
    margin: 0 auto;
    padding: 22px 16px 18px;
    border: 2px solid rgba(255,255,255,.7);
    border-radius: 28px;
    background: #fffaf0;
    box-shadow:
      0 24px 80px rgba(0,0,0,.30),
      0 0 0 6px rgba(224,190,93,.18);
    text-align: center;
    animation: rankCardPop .75s cubic-bezier(.18,.89,.32,1.28) both;
  }

  .rank-celebration-kicker {
    color: #86691f;
    font-size: 12px;
    font-weight: 1000;
    letter-spacing: .16em;
  }

  .rank-celebration-medal {
    width: 132px;
    height: 132px;
    margin: 18px auto 22px;
    border-width: 7px;
    animation:
      medalReveal 1s cubic-bezier(.17,.86,.24,1.35) both;
  }

  .rank-celebration-medal::before,
  .rank-celebration-medal::after {
    top: 100px;
    width: 42px;
    height: 72px;
  }

  .rank-celebration-medal::before { left: 18px; }
  .rank-celebration-medal::after { right: 18px; }

  .rank-celebration-medal .rank-medal-text {
    max-width: 100px;
    font-size: 25px;
  }

  .rank-celebration-title {
    font-size: clamp(28px, 8vw, 42px);
    font-weight: 1000;
    letter-spacing: .02em;
  }

  .rank-celebration-sub {
    margin-top: 8px;
    color: #6d624e;
    font-size: 12px;
    line-height: 1.65;
  }

  .rank-celebration button {
    width: min(260px, 100%);
    margin-top: 18px;
    min-height: 50px;
    font-size: 15px;
  }

  .rank-burst {
    position: absolute;
    left: 50%;
    top: 50%;
    width: 520px;
    height: 520px;
    margin: -260px 0 0 -260px;
    border-radius: 50%;
    background:
      repeating-conic-gradient(
        from 0deg,
        rgba(255,231,122,.48) 0 5deg,
        transparent 5deg 15deg
      );
    animation: rankBurstSpin 14s linear infinite;
  }

  .rank-confetti {
    position: absolute;
    z-index: 2;
    top: -12vh;
    width: 9px;
    height: 20px;
    border-radius: 3px;
    opacity: .95;
    animation: confettiFall var(--fall, 2.8s) linear var(--delay, 0s) infinite;
  }

  @keyframes rankOverlayIn {
    from { opacity: 0; }
    to { opacity: 1; }
  }

  @keyframes rankCardPop {
    0% { transform: scale(.56) translateY(28px); opacity: 0; }
    68% { transform: scale(1.06) translateY(-4px); opacity: 1; }
    100% { transform: scale(1) translateY(0); opacity: 1; }
  }

  @keyframes medalReveal {
    0% { transform: scale(.25) rotate(-24deg); opacity: 0; }
    65% { transform: scale(1.16) rotate(6deg); opacity: 1; }
    100% { transform: scale(1) rotate(0); opacity: 1; }
  }


  @keyframes rankBurstSpin {
    to { transform: rotate(360deg); }
  }

  @keyframes confettiFall {
    0% { transform: translate3d(0, -12vh, 0) rotate(0); }
    100% { transform: translate3d(var(--drift, 30px), 115vh, 0) rotate(720deg); }
  }

  @media (max-width: 760px) {
    .medal-grid {
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }

    .home-rank-track-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 7px;
      margin-bottom: 30px;
    }

    .home-rank-card {
      min-height: 126px;
      flex-direction: column;
      justify-content: flex-start;
      align-items: center;
      gap: 5px;
      padding: 9px 6px;
      text-align: center;
    }

    .home-rank-copy {
      width: 100%;
    }

    .home-rank-label {
      font-size: 9px;
    }

    .home-rank-name {
      font-size: 17px;
    }

    .home-rank-card .app-rank-next {
      font-size: 9px;
      line-height: 1.35;
    }

    .home-rank-medal-coin {
      width: 68px;
      height: 68px;
      flex-basis: 68px;
    }

    .home-rank-medal-image {
      width: 68px;
      height: 68px;
    }

    .home-rank-medal-placeholder {
      width: 60px;
      height: 60px;
    }

    .rank-celebration {
      position: absolute;
      align-items: flex-start;
      padding: 10px 10px 18px;
    }

    .rank-celebration-card {
      width: min(94vw, 360px);
      max-height: none;
      overflow: visible;
      margin: 0 auto;
      padding: 14px 12px 14px;
      border-radius: 20px;
    }

    .rank-celebration-kicker {
      font-size: 10px;
      letter-spacing: .12em;
    }

    .rank-celebration-medal {
      width: 88px;
      height: 88px;
      margin: 10px auto 12px;
      border-width: 5px;
    }

    .rank-celebration-medal::before,
    .rank-celebration-medal::after {
      top: 66px;
      width: 28px;
      height: 46px;
    }

    .rank-celebration-medal::before { left: 12px; }
    .rank-celebration-medal::after { right: 12px; }

    .rank-celebration-medal .rank-medal-text {
      max-width: 72px;
      font-size: 19px;
    }

    .rank-celebration-title {
      font-size: clamp(21px, 7vw, 30px);
      line-height: 1.12;
    }

    .rank-celebration-sub {
      margin-top: 5px;
      font-size: 10px;
      line-height: 1.45;
    }

    .rank-celebration button {
      margin-top: 10px;
      min-height: 42px;
      font-size: 13px;
    }

    .rank-burst {
      top: 165px;
      width: 300px;
      height: 300px;
      margin: -150px 0 0 -150px;
    }
  }


  .hint-btn.recording-disabled {
    opacity: .65;
    cursor: default;
  }

  .video-review-panel {
    margin-top: 18px;
    padding: 16px;
    border: 1px solid #d9d1c4;
    border-radius: 18px;
    background: #fffdf8;
  }

  .video-review-title {
    font-size: 18px;
    font-weight: 1000;
  }

  .video-review-note {
    margin-top: 4px;
    color: #6f685f;
    font-size: 11px;
    line-height: 1.6;
  }

  .video-review-player {
    display: block;
    width: 100%;
    max-height: 52vh;
    margin-top: 12px;
    border-radius: 14px;
    background: #111;
  }

  .video-review-summary {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 8px;
    margin-top: 12px;
  }

  .video-summary-card {
    padding: 10px;
    border-radius: 12px;
    background: #f1ede4;
    text-align: center;
  }

  .video-summary-value {
    font-size: 18px;
    font-weight: 1000;
  }

  .video-summary-label {
    margin-top: 2px;
    color: #726a60;
    font-size: 10px;
    font-weight: 850;
  }

  .video-priority {
    margin-top: 12px;
    padding: 11px 12px;
    border-radius: 12px;
    background: #f6f0df;
    color: #655629;
    font-size: 12px;
    line-height: 1.6;
  }

  .video-question-list {
    display: grid;
    gap: 8px;
    margin-top: 12px;
  }

  .video-question-item {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 10px;
    align-items: center;
    padding: 10px 12px;
    border-radius: 12px;
    background: #f3efe7;
  }

  .video-question-item.wrong {
    border-left: 4px solid #a44b32;
  }

  .video-question-item.correct {
    border-left: 4px solid #437454;
  }

  .video-question-main {
    min-width: 0;
    font-size: 12px;
    line-height: 1.55;
  }

  .video-question-meta {
    color: #756e65;
    font-size: 10px;
  }

  .video-review-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 12px;
  }

  @media (max-width: 760px) {
    .analysis-control {
      align-items: flex-start;
      flex-direction: column;
    }

    .video-review-summary {
      grid-template-columns: 1fr;
    }

    .video-question-item {
      grid-template-columns: 1fr;
    }

    .coaching-issue-actions {
      grid-template-columns: 1fr;
    }

    .camera-dialog {
      width: 100%;
      max-height: none;
      padding: 10px;
      border-radius: 16px;
    }

    .camera-dialog h3 {
      margin-bottom: 4px;
      font-size: 17px;
    }

    .camera-dialog p {
      margin-bottom: 7px;
      font-size: 10px;
      line-height: 1.45;
    }

    .camera-preview-wrap {
      width: min(100%, 320px);
      aspect-ratio: 4 / 3;
      margin: 0 auto;
    }

    .camera-preview {
      width: 100%;
      height: 100%;
      object-fit: cover;
      object-position: center 64%;
    }

    .camera-status {
      margin-top: 6px;
      padding: 7px 9px;
      font-size: 10px;
      line-height: 1.45;
    }

    .camera-actions {
      gap: 6px;
      margin-top: 7px;
    }

    .camera-actions button {
      min-height: 38px;
      padding: 7px 6px;
      font-size: 11px;
    }

    .camera-actions #cameraBeginBtn {
      min-height: 44px;
      font-size: 13px;
    }
  }

  .ranking-modal {
    display: none;
    position: fixed;
    inset: 0;
    z-index: 1000;
    padding: 24px;
    background: rgba(38, 34, 30, .38);
    align-items: center;
    justify-content: center;
  }

  .ranking-modal.show {
    display: flex;
  }

  .ranking-dialog {
    width: min(560px, 96vw);
    max-height: 82vh;
    overflow: hidden;
    padding: 18px;
    border-radius: 18px;
    background: #fff;
    box-shadow: 0 20px 60px rgba(0,0,0,.2);
  }

  .ranking-dialog-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    margin-bottom: 10px;
  }

  .ranking-dialog-title {
    min-width: 0;
    font-size: 15px;
    font-weight: 950;
  }

  .ranking-dialog-close {
    min-height: 30px !important;
    padding: 5px 9px !important;
    font-size: 10px !important;
  }

  .ranking-dialog .ranking-list {
    max-height: 60vh;
  }

  .review {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
    margin-top: 18px;
  }

  .review-item {
    padding: 10px 12px;
    border-radius: 12px;
    background: #f3efe7;
    font-size: 13px;
    line-height: 1.5;
  }

  .review-item.correct { border-left: 4px solid #437454; }
  .review-item.wrong { border-left: 4px solid #a44b32; }
  .review-item.hint { border-left: 4px solid #c59a3b; background: #fff9eb; }

  .actions {
    display: flex;
    justify-content: center;
    gap: 8px;
    flex-wrap: wrap;
    margin-top: 18px;
  }

  @media (prefers-reduced-motion: reduce) {
    .question-card.streak10,
    .rank-celebration,
    .rank-celebration-card,
    .rank-celebration-medal,
    .rank-burst,
    .rank-confetti {
      animation: none !important;
    }
  }

  @media (max-width: 760px) {
    #soroban-app { padding: 8px; }

    .intro {
      flex-direction: column;
      align-items: flex-start;
    }

    .mode-grid { grid-template-columns: 1fr; }
    .mode-card { min-height: 0; }
    .review { grid-template-columns: 1fr; }

    /* ===== チャレンジ中の上部UIを3段に圧縮 ===== */
    .statusbar {
      position: sticky;
      top: 0;
      grid-template-columns: minmax(0, 1fr) auto auto;
      gap: 6px 8px;
      padding: 9px 10px;
      border-radius: 14px;
    }

    .statusbar > div:first-child {
      grid-column: 1 / 3;
      min-width: 0;
    }

    .status-title {
      font-size: 14px;
      line-height: 1.25;
    }

    .status-sub {
      margin-top: 1px;
      font-size: 10px;
    }

    .timer {
      grid-column: 3;
      min-width: 68px;
      font-size: 22px;
    }

    .streak {
      grid-column: 1;
      font-size: 12px;
    }

    .voice-btn {
      grid-column: 2;
      min-height: 36px;
      padding: 6px 9px;
      font-size: 11px;
      white-space: nowrap;
    }

    #bgmBtn {
      grid-column: 3;
      min-height: 36px;
      padding: 6px 9px;
      font-size: 11px;
      white-space: nowrap;
    }

    .challenge-quick-nav {
      grid-column: 1 / -1;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 5px;
    }

    .challenge-quick-nav button {
      min-height: 34px;
      padding: 5px 5px;
      border-radius: 9px;
      font-size: 10px;
      line-height: 1.2;
    }

    /* 状態はボタン自体で分かるため、スマホでは重複2行を省略。 */
    .voice-status,
    .bgm-name {
      display: none !important;
    }

    /* ===== 問題を1画面内に早く見せる ===== */
    .question-card {
      min-height: 0;
      margin-top: 8px;
      padding: 12px 12px 14px;
      border-radius: 18px;
    }

    .qtop {
      gap: 8px;
    }

    .qcount,
    .score {
      font-size: 11px;
    }

    .equation {
      margin: 18px 0 12px;
      font-size: clamp(42px, 13vw, 58px);
      line-height: 1.05;
    }

    .equation.multi-term {
      font-size: clamp(24px, 7vw, 36px);
      line-height: 1.2;
    }

    .equation.multi-term.long-sequence {
      font-size: clamp(20px, 5.6vw, 30px);
    }

    .hint-launch {
      margin: 0 0 10px;
    }

    .hint-btn {
      min-height: 40px;
      padding: 7px 12px;
      font-size: 12px;
    }

    .answer-form {
      gap: 7px;
    }

    .answer-input {
      width: min(250px, 100%);
      min-height: 52px;
      font-size: 27px;
    }

    .answer-form button[type="submit"] {
      min-height: 46px;
      padding: 8px 16px;
      font-size: 14px;
    }

    .keypad-wrap {
      margin-top: 10px;
    }

    .keypad-label {
      margin-bottom: 5px;
      font-size: 11px;
    }

    .keypad {
      gap: 6px;
    }

    .keypad button {
      min-height: 48px;
      font-size: 20px;
    }

    .feedback {
      min-height: 28px;
      margin-top: 8px;
      font-size: 17px;
    }
  }

  .hosu-view { display: none; }
  .hosu-view.show { display: block; }
  .home-mode-btn.hosu-home { background: #f2f8ee; border-color: #a9bc92; }
  .hosu-group h3 { margin: 20px 0 10px; font-size: 22px; }
  .hosu-cards { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
  .hosu-cards .mode-card { display: flex; flex-direction: column; gap: 8px; }
  .hosu-cards button { width: 100%; margin-top: auto; }
  .hosu-record { color: #6d675f; font-size: 12px; }
  .hosu-panel { max-width: 760px; margin: 14px auto; padding: 20px; background: #fff; border: 1px solid #dcd5c8; border-radius: 18px; }
  .hosu-toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; justify-content: space-between; }
  .hosu-equation { text-align: center; font-size: clamp(28px, 7vw, 42px); font-weight: 900; margin: 16px 0 8px; }
  .hosu-count { text-align: center; color: #547047; font-size: 13px; margin-bottom: 12px; }
  .hosu-prompt { font-size: clamp(18px, 4.5vw, 24px); font-weight: 800; line-height: 1.65; margin: 14px 0; }
  .hosu-explanation { background: #fff5de; border-radius: 12px; padding: 12px; line-height: 1.8; }
  .hosu-answer { text-align: center; font-size: 30px; min-height: 40px; }
  .hosu-digits { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 8px; }
  .hosu-digits button { font-size: 23px; background: #eef4e8; min-height: 52px; }
  #hosuNextBtn { width: 100%; margin-top: 14px; }
  #hosuVoiceStatus { font-size: 12px; color: #6d675f; }
  #hosuBoard { margin: 10px auto; max-width: 100%; }
  .hosu-result-score { text-align: center; font-size: 48px; font-weight: 900; margin: 20px 0; }
  @media(max-width: 620px) {
    .hosu-cards { gap: 7px; }
    .hosu-cards .mode-card { padding: 12px 8px; min-width: 0; }
    .hosu-cards .mode-name { font-size: 18px; }
    .hosu-cards .mode-desc, .hosu-cards .chip, .hosu-record { font-size: 11px; }
    .hosu-cards .chips { display: block; }
    .hosu-panel { padding: 14px; }
    .hosu-digits { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  }


  .app-volume-control {
    position: sticky;
    top: 0;
    z-index: 6000;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 12px;
    margin-bottom: 10px;
    background: #f7f5ef;
    border: 1px solid #ddd7ca;
    border-radius: 12px;
    box-shadow: 0 2px 6px rgba(0, 0, 0, .04);
  }
  .app-volume-control label { font-size: 13px; font-weight: 800; white-space: nowrap; }
  #appVolumeSlider { flex: 1; min-width: 0; max-width: 280px; height: 30px; margin: 0; accent-color: #315f86; cursor: pointer; }
  #appVolumeValue { min-width: 4ch; font-size: 12px; color: #6d675f; font-variant-numeric: tabular-nums; }


  .challenge-medal-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; margin-bottom: 8px; }
  .challenge-medal-head .mode-no { min-width: 0; overflow-wrap: anywhere; }
  .challenge-medal-strip { flex-shrink: 0; }



  .hosu-base-choices { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
  .hosu-base-choices button { background: #eef4e8; min-height: 52px; }
  .hosu-intro { margin: 10px 0; font-size: 14px; line-height: 1.7; }
  .kuku-table-head {display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;}
  .kuku-table-grid {display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin:16px 0;}
  .kuku-table-card {background:white;border:1px solid #ddd3c1;border-radius:16px;padding:14px;}
  .kuku-table-card h3 {margin:0 0 10px;display:flex;justify-content:space-between;align-items:center;gap:8px;}
  .kuku-table-card button {font-size:14px;padding:8px 12px;}
  .kuku-table-card table {width:100%;border-collapse:collapse;}
  .kuku-table-card td {padding:7px 4px;border-bottom:1px solid #eee8dd;}
  .kuku-table-card td:first-child {white-space:nowrap;font-weight:700;}
  .kuku-table-card td:last-child {font-size:13px;}
  .kuku-table-card tr.reading {background:#fff0b8;}
  #kukuTableStatus {min-height:1.5em;}
  @media(max-width:760px) {.kuku-table-grid {grid-template-columns:repeat(2,minmax(0,1fr));}}
  @media(max-width:520px) {.kuku-table-grid {grid-template-columns:1fr;}}
  .kuku-game-card {position:relative;transition:border-color .25s ease,border-width .25s ease,box-shadow .25s ease; }
  .kuku-table-scroll {
    max-height: min(60vh, 560px);
    overflow-y: scroll;
    overflow-x: hidden;
    -webkit-overflow-scrolling: touch;
    touch-action: pan-y;
    overscroll-behavior-y: contain;
    scrollbar-gutter: stable;
    scrollbar-width: auto;
    scrollbar-color: #8b7960 #eee7db;
    padding: 0 8px 12px 0;
    border-bottom: 1px solid #ddd3c1;
  }
  .kuku-table-scroll::-webkit-scrollbar {width:12px;}
  .kuku-table-scroll::-webkit-scrollbar-track {background:#eee7db;border-radius:8px;}
  .kuku-table-scroll::-webkit-scrollbar-thumb {background:#8b7960;border-radius:8px;border:2px solid #eee7db;}
  .collection-medal-image {display:block;width:72px;height:72px;max-width:100%;object-fit:contain;filter:drop-shadow(0 3px 4px rgba(55,42,27,.2));}
  .medal-slot.locked .collection-medal-image {filter:grayscale(1);opacity:.22;}
  .diagnostics-buttons {display:flex;flex-wrap:wrap;gap:8px;margin-top:10px;}

#dailyMedalPopup .cm-stamp{width:101px;height:101px;border-radius:50%;border:5px double #b6bfc6;box-shadow:inset 0 6px 13px #ffffffa1,inset 0 -8px 14px #00000011,0 6px 14px #101f2b20;display:flex;align-items:center;justify-content:center;flex-direction:column;margin:0 auto 8px}
#dailyMedalPopup .cm-stamp.gold{background:radial-gradient(circle at 28% 18%,#fff9cf,#f5d361 49%,#c38d1d);border-color:#bd8c26;color:#69470a}
#dailyMedalPopup .cm-stamp.silver{background:radial-gradient(circle at 28% 18%,#fff,#d8e0e8 53%,#9aa8b8);border-color:#9aa9b8;color:#3d5266}
#dailyMedalPopup .cm-stamp.bronze{background:radial-gradient(circle at 28% 18%,#fff1dd,#d99c6e 53%,#a6653d);border-color:#ad7044;color:#60391e}
#dailyMedalPopup .cm-stamp.white{background:radial-gradient(circle at 28% 18%,#fff,#f8f9fb 54%,#d7dde2);border-color:#b9c2cb;color:#4c5b6a}
#dailyMedalPopup .cm-grade{font-size:11px;line-height:1.1;font-weight:850}
#dailyMedalPopup .cm-stamp-char{font-size:37px;font-weight:900;line-height:1.2}
#dailyMedalPopup .cm-stamp-reading{font-size:12px;font-weight:850;line-height:1.1}
  #dailyMedalPopup { position: fixed; inset: 0; z-index: 30000; padding: 16px; box-sizing: border-box; display: flex; align-items: center; justify-content: center; background: rgba(25,30,34,.48); }
  #dailyMedalPopup.hidden { display: none; }
  .daily-medal-card { box-sizing: border-box; width: min(100%,380px); max-height: calc(100dvh - 32px); overflow-y: auto; padding: 24px 20px; border-radius: 22px; background: #fffdf8; text-align: center; box-shadow: 0 12px 40px #0003; }
  #dailyMedalTitle { font-size: 21px; line-height: 1.5; margin: 0 0 18px; overflow-wrap: anywhere; }
  #dailyMedalCategory, #dailyMedalStatus { font-size: 14px; line-height: 1.7; margin: 12px 0; }
  #dailyMedalClose { margin-top: 8px; min-width: 120px; }
</style>
<div class="app-volume-control" role="group" aria-label="アプリ全体の音量">
  <label for="appVolumeSlider">🔊 音量</label>
  <input id="appVolumeSlider" type="range" min="0" max="100" step="1" value="100" aria-valuetext="100%">
  <output id="appVolumeValue" for="appVolumeSlider">100%</output>
</div>


<div id="dailyMedalPopup" class="hidden" role="dialog" aria-modal="true" aria-labelledby="dailyMedalTitle" aria-describedby="dailyMedalStatus">
  <div class="daily-medal-card">
    <h2 id="dailyMedalTitle"></h2>
    <div id="dailyMedalIcon" class="cm-stamp white" role="img"><span id="dailyMedalGrade" class="cm-grade"></span><span id="dailyMedalChar" class="cm-stamp-char"></span><span id="dailyMedalReading" class="cm-stamp-reading"></span></div>
    <p id="dailyMedalCategory"></p><p id="dailyMedalStatus" role="status" aria-live="polite"></p>
    <button type="button" id="dailyMedalClose">閉じる</button>
  </div>
</div>
<div id="homeView" class="app-home">
  <div class="home-hub-nav"><a id="chokomanaHomeLink" href="https://chokomana-hkgx4uyxxezjtr2sj35jwj.streamlit.app/" target="_blank" rel="noopener noreferrer" aria-label="ちょこまなのトップページを別タブで開く">← ちょこまなへ</a></div>
  <div class="home-title">そろばん</div>
  <div class="home-sub">
    チャレンジ・苦手克服・九九即答・暗算から練習方法を選んでください。
  </div>

  <div class="home-rank-track-grid">
    <div class="home-rank-card addsub-track">
      <div
        id="homeAddSubMedal"
        class="home-rank-medal-coin no-rank"
        data-gold-src="__KUKU_GOLD_MEDAL__"
        data-silver-src="__KUKU_SILVER_MEDAL__"
        data-bronze-src="__KUKU_BRONZE_MEDAL__"
      >
        <img class="home-rank-medal-image" alt="足し算・引き算の階級メダル">
        <span class="home-rank-medal-placeholder">－</span>
      </div>
      <div class="home-rank-copy">
        <div class="home-rank-label">足し算・引き算</div>
        <div id="homeAddSubRankName" class="home-rank-name">見習い</div>
        <div id="homeAddSubRankNext" class="app-rank-next">最初の銅メダルを目指そう</div>
      </div>
    </div>

    <div class="home-rank-card muldiv-track">
      <div
        id="homeMulDivMedal"
        class="home-rank-medal-coin no-rank"
        data-gold-src="__KUKU_GOLD_MEDAL__"
        data-silver-src="__KUKU_SILVER_MEDAL__"
        data-bronze-src="__KUKU_BRONZE_MEDAL__"
      >
        <img class="home-rank-medal-image" alt="掛け算・割り算の階級メダル">
        <span class="home-rank-medal-placeholder">－</span>
      </div>
      <div class="home-rank-copy">
        <div class="home-rank-label">掛け算・割り算</div>
        <div id="homeMulDivRankName" class="home-rank-name">見習い</div>
        <div id="homeMulDivRankNext" class="app-rank-next">最初の銅メダルを目指そう</div>
      </div>
    </div>
  </div>

  <div class="home-mode-grid">
    <button type="button" id="homeChallengeBtn" data-app-nav="challenge" class="home-mode-btn primary-home">
      <span class="home-mode-kicker">CHALLENGE</span>
      <span class="home-mode-name">チャレンジモード</span>
      <span class="home-mode-desc">
        12問の計算トレーニング。5分以内の完了で金メダル対象になります。5分を過ぎても最後まで続けられます。
      </span>
    </button>

    <button type="button" id="homeWeaknessBtn" data-app-nav="weakness" class="home-mode-btn weakness-home">
      <span class="home-mode-kicker">REVIEW</span>
      <span class="home-mode-name">苦手克服モード</span>
      <span class="home-mode-desc">
        チャレンジで間違えた問題だけを、レベル別にもう一度練習します。
      </span>
    </button>

    <button type="button" id="homeKukuBtn" data-app-nav="kuku" class="home-mode-btn kuku-home">
      <span class="home-mode-kicker">KUKU</span>
      <span class="home-mode-name">九九名人</span>
      <span class="home-mode-desc">
        九九を見た瞬間に答える練習。掛け算のそろばんへ進む前の基礎力を確認します。
      </span>
    </button>

    <button type="button" id="homeHosuBtn" data-app-nav="hosu" class="home-mode-btn hosu-home">
      <span class="home-mode-kicker">COMPLEMENT</span>
      <span class="home-mode-name">補数名人</span>
      <span class="home-mode-desc">1つの数字を足す・引くときの補数を、1回・2回・3回以上で練習します。</span>
    </button>

    <button type="button" id="homeAnzanBtn" data-app-nav="anzan" class="home-mode-btn anzan-home">
      <span class="home-mode-kicker">MENTAL</span>
      <span class="home-mode-name">暗算モード</span>
      <span class="home-mode-desc">
        数字を順番に見て頭の中で計算。スタート後は答えることに集中できます。
      </span>
    </button>

    <button type="button" id="homeSettingsBtn" data-app-nav="settings" class="home-mode-btn settings-home">
      <span class="home-mode-kicker">SETTINGS</span>
      <span class="home-mode-name">設定</span>
      <span class="home-mode-desc">
        BGM・音声・残り時間表示・暗算速度をまとめて設定します。
      </span>
    </button>
  </div>

  <div id="versionLabel" class="home-version-footer"></div>
</div>



<div id="hosuView" class="hosu-view">
  <div class="subview-topbar">
    <button type="button" data-app-nav="home" class="top-back-btn">← TOPへ</button>
    <div class="subview-topbar-title">補数名人</div>
  </div>
  <div id="hosuMenu">
    <div class="kuku-hero"><h2>補数を順番に使おう</h2><p>1つの数字を足す・引くときに、補数を続けて使う回数で選びます。</p></div>
    <div id="hosuModeGrid"></div>
  </div>
  <div id="hosuGame" class="hosu-panel hidden">
    <div class="hosu-toolbar"><strong id="hosuTitle"></strong><button type="button" id="hosuMenuBtn">モード選択へ</button></div>
    <div id="hosuProgress" class="hosu-record"></div>
    <div class="hosu-toolbar"><button type="button" id="hosuVoiceBtn">🎤 音声回答 OFF</button><span id="hosuVoiceStatus" aria-live="polite"></span></div>
    <div id="hosuEquation" class="hosu-equation"></div>
    <div id="hosuCount" class="hosu-count"></div>
    <p id="hosuIntro" class="hosu-intro hidden"></p>
    <div id="hosuBoard" class="soroban-board"></div>
    <div id="hosuPrompt" class="hosu-prompt" aria-live="polite"></div>
    <button type="button" id="hosuHintBtn">考え方を見る</button>
    <div id="hosuExplanation" class="hosu-explanation hidden"></div>
    <div id="hosuAnswerArea" class="hidden">
      <div id="hosuAnswer" class="hosu-answer" aria-live="polite"></div>
      <div id="hosuBaseChoices" class="hosu-base-choices hidden">
        <button type="button" data-hosu-base="5">5の補数</button>
        <button type="button" data-hosu-base="10">10の補数</button>
      </div>
      <div id="hosuDigits" class="hosu-digits"><button type="button" data-hosu-digit="1">1</button><button type="button" data-hosu-digit="2">2</button><button type="button" data-hosu-digit="3">3</button><button type="button" data-hosu-digit="4">4</button><button type="button" data-hosu-digit="5">5</button><button type="button" data-hosu-digit="6">6</button><button type="button" data-hosu-digit="7">7</button><button type="button" data-hosu-digit="8">8</button><button type="button" data-hosu-digit="9">9</button></div>
    </div>
    <div id="hosuFeedback" class="feedback" aria-live="polite"></div>
    <button type="button" id="hosuNextBtn" class="primary">進む →</button>
  </div>
  <div id="hosuResult" class="hosu-panel hidden">
    <h2>12問おわりました</h2><div id="hosuResultScore" class="hosu-result-score"></div>
    <p id="hosuResultText"></p><p id="hosuSessionCount" class="hosu-record"></p>
    <div class="hosu-toolbar"><button type="button" id="hosuRetryBtn" class="primary">もう一回</button><button type="button" id="hosuResultMenuBtn">モード選択へ</button></div>
  </div>
</div>

<div id="kukuView" class="kuku-view">
  <div class="subview-topbar">
    <button type="button" id="kukuTopBtn" data-app-nav="home" class="top-back-btn">← TOPへ</button>
    <div class="subview-topbar-title">九九名人</div>
  </div>
  <section id="kukuTableView" class="hidden" aria-labelledby="kukuTableTitle">
    <div class="kuku-table-head"><h2 id="kukuTableTitle">九九一覧表</h2><button type="button" id="kukuTableBackBtn">← レベル選択へ</button></div>
    <p>聞きたい段の「読み上げ」を押してね。</p>
    <button type="button" id="kukuTableStopBtn" disabled>読み上げを停止</button>
    <p id="kukuTableStatus" role="status" aria-live="polite"></p>
    <div id="kukuTableScroll" class="kuku-table-scroll" role="region" aria-label="九九一覧表。上下にスクロールできます" tabindex="0">
      <div id="kukuTableGrid" class="kuku-table-grid"></div>
    </div>
  </section>
  <div id="kukuMenuView">
    <button type="button" id="kukuTableOpenBtn" class="primary">九九一覧表</button>
    <div class="kuku-hero">
      <h2>九九を見た瞬間に答える</h2>
      <p>問題は「○掛ける○は？」と読み上げます。音声回答ONなら声で、OFFならスマホの数字ボタンで答えます。</p>
    </div>
    <div class="kuku-level-grid">
      <article class="kuku-level-card" data-kuku-level-card="1">
        <div class="kuku-level-head">
          <div class="kuku-level-no">LEVEL 1｜初級</div>
          <div class="kuku-medal-strip" aria-label="初級のメダル獲得数">
            <span class="kuku-medal-chip gold" title="金メダル"><img class="kuku-medal-image" src="__KUKU_GOLD_MEDAL__" alt="金メダル"><span class="count" data-kuku-medal="gold">×0</span></span>
            <span class="kuku-medal-chip silver" title="銀メダル"><img class="kuku-medal-image" src="__KUKU_SILVER_MEDAL__" alt="銀メダル"><span class="count" data-kuku-medal="silver">×0</span></span>
            <span class="kuku-medal-chip bronze" title="銅メダル"><img class="kuku-medal-image" src="__KUKU_BRONZE_MEDAL__" alt="銅メダル"><span class="count" data-kuku-medal="bronze">×0</span></span>
          </div>
        </div>
        <div class="kuku-level-name">1つの段を昇順</div>
        <div class="kuku-level-desc">1〜9の段から1つをランダムに選び、×1から×10まで順番に10問出題します。</div>
        <div class="kuku-level-meta">10問・時間制限なし</div>
        <button type="button" class="primary start-kuku" data-kuku-level="1">はじめる</button>
      </article>
      <article class="kuku-level-card" data-kuku-level-card="2">
        <div class="kuku-level-head">
          <div class="kuku-level-no">LEVEL 2｜中級</div>
          <div class="kuku-medal-strip" aria-label="中級のメダル獲得数">
            <span class="kuku-medal-chip gold" title="金メダル"><img class="kuku-medal-image" src="__KUKU_GOLD_MEDAL__" alt="金メダル"><span class="count" data-kuku-medal="gold">×0</span></span>
            <span class="kuku-medal-chip silver" title="銀メダル"><img class="kuku-medal-image" src="__KUKU_SILVER_MEDAL__" alt="銀メダル"><span class="count" data-kuku-medal="silver">×0</span></span>
            <span class="kuku-medal-chip bronze" title="銅メダル"><img class="kuku-medal-image" src="__KUKU_BRONZE_MEDAL__" alt="銅メダル"><span class="count" data-kuku-medal="bronze">×0</span></span>
          </div>
        </div>
        <div class="kuku-level-name">昇順または降順</div>
        <div class="kuku-level-desc">1〜9の段から1つをランダムに選び、×1→×10または×10→×1で10問出題します。音声は一般的な九九の唱え方です。</div>
        <div class="kuku-level-meta">10問・60秒</div>
        <button type="button" class="primary start-kuku" data-kuku-level="2">はじめる</button>
      </article>
      <article class="kuku-level-card" data-kuku-level-card="3">
        <div class="kuku-level-head">
          <div class="kuku-level-no">LEVEL 3｜上級</div>
          <div class="kuku-medal-strip" aria-label="上級のメダル獲得数">
            <span class="kuku-medal-chip gold" title="金メダル"><img class="kuku-medal-image" src="__KUKU_GOLD_MEDAL__" alt="金メダル"><span class="count" data-kuku-medal="gold">×0</span></span>
            <span class="kuku-medal-chip silver" title="銀メダル"><img class="kuku-medal-image" src="__KUKU_SILVER_MEDAL__" alt="銀メダル"><span class="count" data-kuku-medal="silver">×0</span></span>
            <span class="kuku-medal-chip bronze" title="銅メダル"><img class="kuku-medal-image" src="__KUKU_BRONZE_MEDAL__" alt="銅メダル"><span class="count" data-kuku-medal="bronze">×0</span></span>
          </div>
        </div>
        <div class="kuku-level-name">完全ランダム10問</div>
        <div class="kuku-level-desc">1×1〜9×10から重複なしでランダムに10問出題します。音声は一般的な九九の唱え方です。</div>
        <div class="kuku-level-meta">10問・60秒</div>
        <button type="button" class="primary start-kuku" data-kuku-level="3">はじめる</button>
      </article>
      <article class="kuku-level-card" data-kuku-level-card="4">
        <div class="kuku-level-head">
          <div class="kuku-level-no">LEVEL 4｜特級</div>
          <div class="kuku-medal-strip" aria-label="特級のメダル獲得数">
            <span class="kuku-medal-chip gold" title="金メダル"><img class="kuku-medal-image" src="__KUKU_GOLD_MEDAL__" alt="金メダル"><span class="count" data-kuku-medal="gold">×0</span></span>
            <span class="kuku-medal-chip silver" title="銀メダル"><img class="kuku-medal-image" src="__KUKU_SILVER_MEDAL__" alt="銀メダル"><span class="count" data-kuku-medal="silver">×0</span></span>
            <span class="kuku-medal-chip bronze" title="銅メダル"><img class="kuku-medal-image" src="__KUKU_BRONZE_MEDAL__" alt="銅メダル"><span class="count" data-kuku-medal="bronze">×0</span></span>
          </div>
        </div>
        <div class="kuku-level-name">完全ランダム30問</div>
        <div class="kuku-level-desc">1×1〜9×10から重複なしでランダムに30問出題します。音声は一般的な九九の唱え方です。</div>
        <div class="kuku-level-meta">30問・90秒</div>
        <button type="button" class="primary start-kuku" data-kuku-level="4">はじめる</button>
      </article>
      <article class="kuku-level-card" data-kuku-level-card="5">
        <div class="kuku-level-head">
          <div class="kuku-level-no">LEVEL 5｜名人</div>
          <div class="kuku-medal-strip" aria-label="名人のメダル獲得数">
            <span class="kuku-medal-chip gold" title="金メダル"><img class="kuku-medal-image" src="__KUKU_GOLD_MEDAL__" alt="金メダル"><span class="count" data-kuku-medal="gold">×0</span></span>
            <span class="kuku-medal-chip silver" title="銀メダル"><img class="kuku-medal-image" src="__KUKU_SILVER_MEDAL__" alt="銀メダル"><span class="count" data-kuku-medal="silver">×0</span></span>
            <span class="kuku-medal-chip bronze" title="銅メダル"><img class="kuku-medal-image" src="__KUKU_BRONZE_MEDAL__" alt="銅メダル"><span class="count" data-kuku-medal="bronze">×0</span></span>
          </div>
        </div>
        <div class="kuku-level-name">九九90問すべて</div>
        <div class="kuku-level-desc">1×1〜9×10の全90問を、それぞれ1回ずつ完全ランダムで出題します。音声は一般的な九九の唱え方です。</div>
        <div class="kuku-level-meta">90問・240秒</div>
        <button type="button" class="primary start-kuku" data-kuku-level="5">はじめる</button>
      </article>
    </div>
  </div>
  <div id="kukuGameView" class="hidden">
    <div class="kuku-game-card">
      <div class="kuku-status">
        <span id="kukuQCount">1 / 10</span>
        <span id="kukuTimer" class="kuku-timer">--:--</span>
        <span id="kukuCorrectCount">正解 0</span>
      </div>
      <div id="kukuEquation" class="kuku-equation">2 × 3 = ?</div>
      <div id="kukuPrompt" class="kuku-prompt">問題を読み上げます</div>
      <div class="kuku-controls">
        <button type="button" id="kukuVoiceBtn">🎤 音声回答 OFF</button>
      </div>
      <div id="kukuAnswerDisplay" class="kuku-answer-display">&nbsp;</div>
      <div id="kukuKeypad" class="kuku-keypad">
        <button type="button" data-kuku-key="7">7</button><button type="button" data-kuku-key="8">8</button><button type="button" data-kuku-key="9">9</button>
        <button type="button" data-kuku-key="4">4</button><button type="button" data-kuku-key="5">5</button><button type="button" data-kuku-key="6">6</button>
        <button type="button" data-kuku-key="1">1</button><button type="button" data-kuku-key="2">2</button><button type="button" data-kuku-key="3">3</button>
        <button type="button" data-kuku-action="clear">クリア</button><button type="button" data-kuku-key="0">0</button><button type="button" data-kuku-action="backspace">← 1つ消す</button>
      </div>
      <button type="button" id="kukuSubmitBtn" class="primary">答える</button>
      <div id="kukuFeedback" class="kuku-feedback"></div>
    </div>
  </div>
  <div id="kukuResultView" class="hidden">
    <div class="kuku-result-card">
      <div>九九名人終了</div>
      <div id="kukuResultScore" class="kuku-result-score">0 / 9</div>
      <div id="kukuResultText" class="kuku-prompt"></div>
      <div class="kuku-actions">
        <button type="button" id="kukuRetryBtn" class="primary">同じレベルをもう一回</button>
        <button type="button" id="kukuMenuBtn">レベル選択へ</button>
        <button type="button" data-app-nav="home">← TOPへ</button>
      </div>
    </div>
  </div>
</div>

<div id="weaknessView" class="weakness-view">
  <div class="subview-topbar">
    <button type="button" id="weaknessTopBtn" data-app-nav="home" class="top-back-btn">← TOPへ</button>
    <div class="subview-topbar-title">苦手克服モード</div>
  </div>

  <div class="anzan-hero">
    <h2>間違えた問題だけを練習</h2>
    <p>通常チャレンジで間違えた問題を保存しています。未克服問題がないレベルは選択できません。</p>
  </div>

  <div class="challenge-operation-nav">
    <button type="button" class="weakness-operation-jump" data-target="weak-add">足し算</button>
    <button type="button" class="weakness-operation-jump" data-target="weak-sub">引き算</button>
    <button type="button" class="weakness-operation-jump" data-target="weak-mul">掛け算</button>
    <button type="button" class="weakness-operation-jump" data-target="weak-div">割り算</button>
  </div>

  <div id="weaknessChallengeGrid"></div>
</div>


<div id="anzanView" class="anzan-view">
  <div class="subview-topbar">
    <button type="button" id="anzanTopBtn" data-app-nav="home" onclick="window.__sorobanHardNav && window.__sorobanHardNav('home'); return false;" class="top-back-btn">← TOPへ</button>
    <div class="subview-topbar-title">暗算モード</div>
  </div>

  <div id="anzanMenuView">
    <div class="anzan-hero">
      <h2>見て、頭の中で計算</h2>
      <p>
        「はじめる」を押した後は数字が自動で進みます。
        そろばんを頭に思い浮かべて、最後の答えだけ入力します。
      </p>
    </div>

    <div class="anzan-level-grid">
      <article class="anzan-level-card">
        <div class="anzan-level-no">LEVEL 1</div>
        <div class="anzan-level-name">1桁・3口</div>
        <div class="anzan-level-desc">
          1〜9の足し算を3回。暗算を始める最初のステップです。
        </div>
        <button type="button" class="primary start-anzan" data-anzan-level="1">はじめる</button>
      </article>

      <article class="anzan-level-card">
        <div class="anzan-level-no">LEVEL 2</div>
        <div class="anzan-level-name">1桁・5口</div>
        <div class="anzan-level-desc">
          1桁の足し算・引き算を5回。途中の答えは0未満になりません。
        </div>
        <button type="button" class="primary start-anzan" data-anzan-level="2">はじめる</button>
      </article>

      <article class="anzan-level-card">
        <div class="anzan-level-no">LEVEL 3</div>
        <div class="anzan-level-name">2桁・5口</div>
        <div class="anzan-level-desc">
          10〜49を使う足し算・引き算。位を頭の中で保つ練習です。
        </div>
        <button type="button" class="primary start-anzan" data-anzan-level="3">はじめる</button>
      </article>
    </div>
  </div>

  <div id="anzanGameView" class="hidden">
    <div class="anzan-game-card">
      <div class="anzan-status">
        <span id="anzanQCount">1 / 10</span>
        <span id="anzanCorrectCount">正解 0</span>
        <span id="anzanSpeedLabel">ゆっくり</span>
      </div>

      <div class="kuku-controls"><button type="button" id="anzanVoiceBtn" aria-pressed="false">🎤 音声回答 OFF</button></div>
      <div id="anzanFlash" class="anzan-flash ready">よーい</div>
      <div id="anzanHint" class="anzan-hint">数字を順番に見てね</div>

      <div id="anzanAnswerArea" class="hidden">
        <div id="anzanAnswerDisplay" class="anzan-answer-display">&nbsp;</div>
        <div id="anzanVoiceStatus" class="anzan-hint"></div>

        <div id="anzanKeypad" class="anzan-keypad">
          <button type="button" data-anzan-key="7">7</button>
          <button type="button" data-anzan-key="8">8</button>
          <button type="button" data-anzan-key="9">9</button>
          <button type="button" data-anzan-key="4">4</button>
          <button type="button" data-anzan-key="5">5</button>
          <button type="button" data-anzan-key="6">6</button>
          <button type="button" data-anzan-key="1">1</button>
          <button type="button" data-anzan-key="2">2</button>
          <button type="button" data-anzan-key="3">3</button>
          <button type="button" data-anzan-action="clear">クリア</button>
          <button type="button" data-anzan-key="0">0</button>
          <button type="button" data-anzan-action="backspace">← 1つ消す</button>
        </div>

        <button type="button" id="anzanSubmitBtn" class="primary">答える</button>
      </div>

      <div id="anzanFeedback" class="anzan-feedback"></div>
    </div>
  </div>

  <div id="anzanResultView" class="hidden">
    <div class="anzan-result">
      <div>暗算10問終了</div>
      <div id="anzanResultScore" class="anzan-result-score">0 / 10</div>
      <div id="anzanResultText" class="anzan-hint"></div>
      <div class="anzan-actions">
        <button type="button" id="anzanRetryBtn" class="primary">同じレベルをもう10問</button>
        <button type="button" id="anzanMenuBtn">レベル選択へ</button>
      </div>
    </div>
  </div>
</div>

<div id="settingsView" class="settings-view"><p id="chokomanaLinkStatus" style="font-size:0.85rem;color:#666">ちょこまな連携：未接続</p><button type="button" id="chokomanaExportBtn">学習ログを出力</button>
  <div class="subview-topbar">
    <button type="button" id="settingsTopBtn" data-app-nav="home" onclick="window.__sorobanHardNav && window.__sorobanHardNav('home'); return false;" class="top-back-btn">← TOPへ</button>
    <div class="subview-topbar-title">設定</div>
  </div>

  <div class="settings-hero">
    <h2>設定</h2>
    <p>
      子どもが毎回設定を触らなくてよいよう、ここでまとめて保存します。
    </p>
  </div>

  <div class="settings-grid">
    <article class="setting-card">
      <div class="setting-title">残り時間の表示</div>
      <div class="setting-desc">5分の残り時間を画面に表示するか選びます。0:00になってもチャレンジは続きます。</div>
      <div id="settingTimeValue" class="setting-value">表示する</div>
      <button type="button" id="settingTimeBtn">切り替える</button>
    </article>

    <article class="setting-card">
      <div class="setting-title">チャレンジの音声回答</div>
      <div class="setting-desc">チャレンジ開始時から音声回答を使う設定です。</div>
      <div id="settingVoiceValue" class="setting-value">OFF</div>
      <button type="button" id="settingVoiceBtn">切り替える</button>
    </article>

    <article class="setting-card">
      <div class="setting-title">BGM</div>
      <div class="setting-desc">チャレンジ中のBGMを最初からON/OFFにします。マイクON中も音楽は流れ、答えを話した瞬間だけ自動で下がります。</div>
      <div id="settingBgmValue" class="setting-value">ON</div>
      <button type="button" id="settingBgmBtn">切り替える</button>
    </article>

    <article class="setting-card">
      <div class="setting-title">学習モードの音声解説</div>
      <div class="setting-desc">学習STEPを開いたときの音声解説の初期状態です。</div>
      <div id="settingLearningVoiceValue" class="setting-value">OFF</div>
      <button type="button" id="settingLearningVoiceBtn">切り替える</button>
    </article>

    <article class="setting-card">
      <div class="setting-title">暗算の数字表示速度</div>
      <div class="setting-desc">数字1つを画面に表示する時間です。</div>
      <div id="settingAnzanSpeedValue" class="setting-value">ゆっくり</div>
      <button type="button" id="settingAnzanSpeedBtn">速度を変える</button>
    </article>
  </div>

  <div class="app-rank-card">
    <div class="app-rank-head">
      <div>
        <div class="app-rank-title">現在のアプリ内階級（2系統）</div>
        <div id="appRankSub" class="app-rank-next">クリアした難易度と正答数から自動認定します。</div>
      </div>
      <div id="appRankBadge" class="app-rank-badge">見習い</div>
    </div>
    <div class="app-rank-meter">
      <div id="appRankMeterFill" class="app-rank-meter-fill"></div>
    </div>
    <div id="appRankNext" class="app-rank-next"></div>
    <div class="app-rank-note">
      足し算・引き算と、掛け算・割り算を別々に認定します。上位の級・段へ進むには、それ以前の全モードで金条件を満たす必要があります。公式の珠算検定とは別のアプリ内称号です。
    </div>
  </div>

  <div class="medal-collection">
    <div class="medal-collection-title">獲得メダル</div>
    <div class="medal-collection-note">
      各級・段ごとに銅・銀・金のメダルを保存します。珠ヒントを使った問題は正解数には入りません。
    </div>
    <div id="medalCollectionGrid" class="medal-grid"></div>

    <details class="medal-conditions">
      <summary>メダル獲得条件を見る</summary>
      <div id="medalConditionList" class="medal-condition-list"></div>
    </details>

    <div class="medal-reset-box">
      <div class="medal-reset-title">メダル獲得状況をリセット</div>
      <div class="medal-reset-note">
        メダルを最初から取り直せるよう、階級認定の進捗も同時にリセットします。チャレンジ履歴・得点ランキング・各種設定は残します。
      </div>
      <button type="button" id="medalResetBtn" class="medal-reset-btn">メダルをリセット</button>
      <div id="medalResetStatus" class="medal-reset-status"></div>
    </div>
  </div>

  <section id="diagnosticsPanel" class="medal-collection" aria-labelledby="diagnosticsTitle">
    <h3 id="diagnosticsTitle">動作ログ</h3>
    <p class="setting-desc">UI・動作速度の改善用です。操作時間、画面更新の推定時間、音声・BGMの待ち時間、停止やエラーをこの端末に記録します。音声・認識内容・入力した答えは保存しません。</p>
    <p class="setting-desc">直近最大2,000件を保存し、古いログから削除します。端末容量により件数が少なくなる場合があります。問題が起きた直後にJSONを出力してください。</p>
    <p id="diagnosticsStatus" role="status"></p>
    <div class="diagnostics-buttons">
      <button type="button" id="diagnosticsToggle">記録を停止</button>
      <button type="button" id="diagnosticsJson">JSONを出力</button>
      <button type="button" id="diagnosticsCsv">CSVを出力</button>
      <button type="button" id="diagnosticsClear">ログを消去</button>
    </div>
    <p class="setting-desc">表示完了時間は推定値です。サーバー起動・データベース処理は直接計測できません。ログの保存・停止は学習記録に影響しません。</p>
  </section>

  <div class="settings-save-note">
    設定はこの端末のブラウザに自動保存されます。暗算モードは、音声回答をONにしておくと答えるときの画面操作も減らせます。
  </div>
</div>

<div id="rankCelebration" class="rank-celebration" aria-hidden="true">
  <div class="rank-burst"></div>
  <div id="rankConfettiLayer"></div>
  <div class="rank-celebration-card">
    <div class="rank-celebration-kicker">メダル獲得！</div>
    <div id="rankCelebrationMedal" class="rank-medal rank-celebration-medal">
      <span id="rankCelebrationMedalText" class="rank-medal-text">10級</span>
    </div>
    <div id="rankCelebrationTitle" class="rank-celebration-title">10級 認定！</div>
    <div id="rankCelebrationSub" class="rank-celebration-sub"></div>
    <button type="button" id="rankCelebrationClose" class="primary">メダルを受け取る</button>
  </div>
</div>

<div id="menuView" class="hidden">
  <div class="subview-topbar">
    <button type="button" id="challengeTopBtn" data-app-nav="home" onclick="window.__sorobanHardNav && window.__sorobanHardNav('home'); return false;" class="top-back-btn">← TOPへ</button>
    <div class="subview-topbar-title">チャレンジモード</div>
  </div>
  <div class="intro">
    <div class="lead">
      各モード12問です。
      割り算以外は、計算式を確定する直前に左右の数へ必ず+1します。
      そのため表示される数に0は出ません。
    </div>
    <div id="modeTimeBadge" class="badge">12問 / 金メダル基準5分</div>
  </div>

  <div class="time-limit-control">
    <span class="time-limit-label">残り時間</span>
    <button type="button" id="timeLimitBtn" class="time-limit-toggle">
      表示する
    </button>
  </div>

  <div class="analysis-control hidden">
    <div>
      <div class="analysis-control-title">🎥 動画で振り返り</div>
      <div class="analysis-control-note">
        インカメラで手元とそろばんを撮影し、問題ごとの時刻と自動で同期します。
        録画は映像のみで、音声認識用マイクとは分けます。
      </div>
    </div>
    <button type="button" id="analysisVideoToggle" class="time-limit-toggle">
      OFF
    </button>
  </div>

  <div id="challengeResumeCard" class="challenge-resume-card hidden">
    <div class="challenge-resume-title">前回のチャレンジがあります</div>
    <div id="challengeResumeText" class="challenge-resume-text"></div>
    <div class="challenge-resume-actions">
      <button type="button" id="resumeChallengeBtn" class="primary">続きから再開</button>
      <button type="button" id="discardResumeBtn">再開データを消す</button>
    </div>
  </div>

  <div id="nextRankGuide" class="next-rank-guide">
    <div id="nextRankGuideTitle" class="next-rank-guide-title">次の級・段まで</div>
    <div id="nextRankGuideText" class="next-rank-guide-text"></div>
  </div>

  <div class="challenge-operation-nav" aria-label="計算の種類">
    <button type="button" class="challenge-operation-jump" data-target="challenge-add">足し算</button>
    <button type="button" class="challenge-operation-jump" data-target="challenge-sub">引き算</button>
    <button type="button" class="challenge-operation-jump" data-target="challenge-mul">掛け算</button>
    <button type="button" class="challenge-operation-jump" data-target="challenge-div">割り算</button>
  </div>

  <div id="challenge-add" class="level-title mode-section-anchor">足し算</div>
  <div class="mode-grid">
    <article class="mode-card">
      <div class="mode-no">BEGINNER ADD 1</div>
      <div class="mode-name">1桁・繰り上がりなし</div>
      <div class="mode-desc">1〜9同士。一の位から十の位への繰り上がりがない12問です。</div>
      <div class="chips"><span class="chip">12問</span><span class="chip time-chip">金:5分以内</span></div>
      <button type="button" class="primary start-mode" data-mode="ba1">はじめる</button>
    </article>

    <article class="mode-card">
      <div class="mode-no">BEGINNER ADD 2</div>
      <div class="mode-name">1桁・繰り上がりあり</div>
      <div class="mode-desc">1〜9同士。一の位から十の位へ必ず繰り上がる12問です。</div>
      <div class="chips"><span class="chip">12問</span><span class="chip time-chip">金:5分以内</span></div>
      <button type="button" class="primary start-mode" data-mode="ba2">はじめる</button>
    </article>

    <article class="mode-card">
      <div class="mode-no">BEGINNER ADD 3</div>
      <div class="mode-name">1桁の数を4つ足す</div>
      <div class="mode-desc">1桁の数を4つ、左から順番に足す連続足し算です。</div>
      <div class="chips"><span class="chip">12問</span><span class="chip time-chip">金:5分以内</span></div>
      <button type="button" class="primary start-mode" data-mode="ba2x4">はじめる</button>
    </article>

    <article class="mode-card">
      <div class="mode-no">BEGINNER ADD 4</div>
      <div class="mode-name">2桁・繰り上がりなし</div>
      <div class="mode-desc">10〜99同士。一の位から十の位への繰り上がりがない2桁レベルです。</div>
      <div class="chips"><span class="chip">12問</span><span class="chip time-chip">金:5分以内</span></div>
      <button type="button" class="primary start-mode" data-mode="ba3">はじめる</button>
    </article>

    <article class="mode-card">
      <div class="mode-no">BEGINNER ADD 5</div>
      <div class="mode-name">2桁・繰り上がりあり</div>
      <div class="mode-desc">10〜99同士。一の位から十の位へ必ず繰り上がる2桁レベルです。</div>
      <div class="chips"><span class="chip">12問</span><span class="chip time-chip">金:5分以内</span></div>
      <button type="button" class="primary start-mode" data-mode="ba4">はじめる</button>
    </article>

    <article class="mode-card">
      <div class="mode-no">BEGINNER ADD 6</div>
      <div class="mode-name">2桁の数を4つ足す</div>
      <div class="mode-desc">2桁の数を4つ、左から順番に足す連続足し算です。</div>
      <div class="chips"><span class="chip">12問</span><span class="chip time-chip">金:5分以内</span></div>
      <button type="button" class="primary start-mode" data-mode="ba4x4">はじめる</button>
    </article>

    <article class="mode-card">
      <div class="mode-no">BEGINNER ADD 7</div>
      <div class="mode-name">3桁の足し算</div>
      <div class="mode-desc">100〜999同士を足す3桁の足し算です。</div>
      <div class="chips"><span class="chip">12問</span><span class="chip time-chip">金:5分以内</span></div>
      <button type="button" class="primary start-mode" data-mode="ba5">はじめる</button>
    </article>

    <article class="mode-card">
      <div class="mode-no">BEGINNER ADD 8</div>
      <div class="mode-name">3桁の数を4つ足す</div>
      <div class="mode-desc">3桁の数を4つ、左から順番に足す連続足し算です。</div>
      <div class="chips"><span class="chip">12問</span><span class="chip time-chip">金:5分以内</span></div>
      <button type="button" class="primary start-mode" data-mode="ba5x4">はじめる</button>
    </article>
  </div>

  <div id="challenge-sub" class="level-title mode-section-anchor">引き算</div>
  <div class="mode-grid">
    <article class="mode-card">
      <div class="mode-no">BEGINNER SUB 1</div>
      <div class="mode-name">1桁・繰り下がりなし</div>
      <div class="mode-desc">1〜9同士。一の位だけで引ける、繰り下がりなしの12問です。</div>
      <div class="chips"><span class="chip">12問</span><span class="chip time-chip">金:5分以内</span></div>
      <button type="button" class="primary start-mode" data-mode="bs1">はじめる</button>
    </article>

    <article class="mode-card">
      <div class="mode-no">BEGINNER SUB 2</div>
      <div class="mode-name">1桁を引く・繰り下がりあり</div>
      <div class="mode-desc">10〜18から1〜9を引き、十の位から必ず繰り下がる12問です。</div>
      <div class="chips"><span class="chip">12問</span><span class="chip time-chip">金:5分以内</span></div>
      <button type="button" class="primary start-mode" data-mode="bs2">はじめる</button>
    </article>

    <article class="mode-card">
      <div class="mode-no">BEGINNER SUB 3</div>
      <div class="mode-name">2桁から1桁の数を3回引く</div>
      <div class="mode-desc">10〜99から、1〜9の数を3回引きます。途中と答えは0以上です。</div>
      <div class="chips"><span class="chip">12問</span><span class="chip time-chip">金:5分以内</span></div>
      <button type="button" class="primary start-mode" data-mode="bs2x4">はじめる</button>
    </article>

    <article class="mode-card">
      <div class="mode-no">BEGINNER SUB 4</div>
      <div class="mode-name">2桁・繰り下がりなし</div>
      <div class="mode-desc">10〜99同士。一の位から十の位への繰り下がりがない2桁レベルです。</div>
      <div class="chips"><span class="chip">12問</span><span class="chip time-chip">金:5分以内</span></div>
      <button type="button" class="primary start-mode" data-mode="bs3">はじめる</button>
    </article>

    <article class="mode-card">
      <div class="mode-no">BEGINNER SUB 5</div>
      <div class="mode-name">2桁・繰り下がりあり</div>
      <div class="mode-desc">10〜99同士。一の位の不足で十の位から必ず繰り下がる2桁レベルです。</div>
      <div class="chips"><span class="chip">12問</span><span class="chip time-chip">金:5分以内</span></div>
      <button type="button" class="primary start-mode" data-mode="bs4">はじめる</button>
    </article>

    <article class="mode-card">
      <div class="mode-no">BEGINNER SUB 6</div>
      <div class="mode-name">2桁の数を4つ使う引き算</div>
      <div class="mode-desc">2桁の数4つを使い、左から順番に引きます。途中と答えは0以上です。</div>
      <div class="chips"><span class="chip">12問</span><span class="chip time-chip">金:5分以内</span></div>
      <button type="button" class="primary start-mode" data-mode="bs4x4">はじめる</button>
    </article>

    <article class="mode-card">
      <div class="mode-no">BEGINNER SUB 7</div>
      <div class="mode-name">3桁の引き算</div>
      <div class="mode-desc">100〜999同士の引き算です。答えは0以上です。</div>
      <div class="chips"><span class="chip">12問</span><span class="chip time-chip">金:5分以内</span></div>
      <button type="button" class="primary start-mode" data-mode="bs5">はじめる</button>
    </article>

    <article class="mode-card">
      <div class="mode-no">BEGINNER SUB 8</div>
      <div class="mode-name">3桁から2桁を4回引く</div>
      <div class="mode-desc">大きい3桁の数から、2桁の数を4回続けて引きます。途中と答えは0以上です。</div>
      <div class="chips"><span class="chip">12問</span><span class="chip time-chip">金:5分以内</span></div>
      <button type="button" class="primary start-mode" data-mode="bs5x4">はじめる</button>
    </article>
  </div>

  <div id="challenge-mul" class="level-title mode-section-anchor">掛け算</div>
  <div class="mode-grid">
    <article class="mode-card">
      <div class="mode-no">INTERMEDIATE MUL 1</div>
      <div class="mode-name">1桁×1桁</div>
      <div class="mode-desc">1〜9同士の掛け算のみ12問です。</div>
      <div class="chips"><span class="chip">12問</span><span class="chip time-chip">金:5分以内</span></div>
      <button type="button" class="primary start-mode" data-mode="mm1">はじめる</button>
    </article>

    <article class="mode-card">
      <div class="mode-no">INTERMEDIATE MUL 2</div>
      <div class="mode-name">2桁×1桁</div>
      <div class="mode-desc">2桁×1桁の掛け算のみ12問です。</div>
      <div class="chips"><span class="chip">12問</span><span class="chip time-chip">金:5分以内</span></div>
      <button type="button" class="primary start-mode" data-mode="mm2">はじめる</button>
    </article>

    <article class="mode-card">
      <div class="mode-no">INTERMEDIATE MUL 3</div>
      <div class="mode-name">2桁×2桁</div>
      <div class="mode-desc">2桁同士の掛け算のみ12問です。</div>
      <div class="chips"><span class="chip">12問</span><span class="chip time-chip">金:5分以内</span></div>
      <button type="button" class="primary start-mode" data-mode="mm3">はじめる</button>
    </article>
  </div>

  <div id="challenge-div" class="level-title mode-section-anchor">割り算</div>
  <div class="mode-grid">
    <article class="mode-card">
      <div class="mode-no">INTERMEDIATE DIV 1</div>
      <div class="mode-name">1〜81 ÷ 1桁</div>
      <div class="mode-desc">1〜81を1桁で割り、答えが整数になる割り算のみ12問です。</div>
      <div class="chips"><span class="chip">12問</span><span class="chip time-chip">金:5分以内</span></div>
      <button type="button" class="primary start-mode" data-mode="md1">はじめる</button>
    </article>

    <article class="mode-card">
      <div class="mode-no">INTERMEDIATE DIV 2</div>
      <div class="mode-name">3桁÷1桁</div>
      <div class="mode-desc">100〜999を1桁で割り、答えが整数になる割り算のみ12問です。</div>
      <div class="chips"><span class="chip">12問</span><span class="chip time-chip">金:5分以内</span></div>
      <button type="button" class="primary start-mode" data-mode="md2">はじめる</button>
    </article>

    <article class="mode-card">
      <div class="mode-no">INTERMEDIATE DIV 3</div>
      <div class="mode-name">3桁÷2桁</div>
      <div class="mode-desc">100〜999を2桁で割り、答えが整数になる割り算のみ12問です。</div>
      <div class="chips"><span class="chip">12問</span><span class="chip time-chip">金:5分以内</span></div>
      <button type="button" class="primary start-mode" data-mode="md3">はじめる</button>
    </article>
  </div>

  <div id="challenge-advanced" class="level-title mode-section-anchor">上級総合</div>
  <div class="mode-grid">
    <article class="mode-card">
      <div class="mode-no">ADVANCED 1</div>
      <div class="mode-name">4桁の足し算・引き算</div>
      <div class="mode-desc">最終表示は1000〜9999。引き算の答えは0以上です。</div>
      <div class="chips"><span class="chip">12問</span><span class="chip time-chip">金:5分以内</span></div>
      <button type="button" class="primary start-mode" data-mode="a1">はじめる</button>
    </article>

    <article class="mode-card">
      <div class="mode-no">ADVANCED 2</div>
      <div class="mode-name">3桁×2桁 / 4桁÷2桁</div>
      <div class="mode-desc">3桁×2桁の掛け算と、4桁÷2桁の整数解です。</div>
      <div class="chips"><span class="chip">12問</span><span class="chip time-chip">金:5分以内</span></div>
      <button type="button" class="primary start-mode" data-mode="a2">はじめる</button>
    </article>

    <article class="mode-card">
      <div class="mode-no">ADVANCED 3</div>
      <div class="mode-name">3桁×3桁 / 5桁÷3桁</div>
      <div class="mode-desc">3桁同士の掛け算と、5桁÷3桁の整数解です。</div>
      <div class="chips"><span class="chip">12問</span><span class="chip time-chip">金:5分以内</span></div>
      <button type="button" class="primary start-mode" data-mode="a3">はじめる</button>
    </article>
  </div>

  <div id="rankingModal" class="ranking-modal" aria-hidden="true">
    <div class="ranking-dialog">
      <div class="ranking-dialog-head">
        <div id="rankingModalTitle" class="ranking-dialog-title">
          過去の得点ランキング
        </div>
        <button type="button" id="rankingModalClose" class="ranking-dialog-close">
          閉じる
        </button>
      </div>
      <div class="ranking-note">
        このブラウザに保存された記録です。親御さんの記録などは「削除」で1件ずつ消せます。
      </div>
      <div id="rankingModalList" class="ranking-list"></div>
    </div>
  </div>
</div>


<div id="learningView" class="learning-view">
  <div class="subview-topbar">
    <button type="button" id="learningTopBtn" data-app-nav="home" onclick="window.__sorobanHardNav && window.__sorobanHardNav('home'); return false;" class="top-back-btn">← TOPへ</button>
    <div class="subview-topbar-title">学習モード</div>
  </div>

  <div id="learningCategoryView">
    <div class="learning-hero">
      <h2>珠の動かし方を順番に学ぶ</h2>
      <p>
        まず動画のような珠の動きを見て、ポイントを確認し、最後に理解チェックをします。
        各計算はSTEP 1から少しずつ難しくなります。
      </p>
      <div id="learningOverallText" class="learning-progress-summary"></div>
      <div class="learning-progress-track">
        <div id="learningOverallBar" class="learning-progress-bar"></div>
      </div>
    </div>

    <div id="learningCategoryGrid" class="learning-category-grid"></div>
  </div>

  <div id="learningStageView" class="hidden">
    <div class="learning-lesson-head">
      <div>
        <div id="learningStageKicker" class="learning-lesson-kicker"></div>
        <div id="learningStageHeading" class="learning-lesson-title"></div>
      </div>
      <button type="button" id="learningStageBackBtn">← 計算の種類へ</button>
    </div>

    <div id="learningStageGrid" class="learning-stage-grid"></div>
  </div>

  <div id="learningLessonView" class="hidden">
    <div class="learning-lesson-head">
      <div>
        <div id="learningLessonKicker" class="learning-lesson-kicker"></div>
        <div id="learningLessonTitle" class="learning-lesson-title"></div>
      </div>
      <button type="button" id="learningLessonBackBtn">← STEP一覧へ</button>
    </div>

    <div class="learning-example-card">
      <div class="learning-example-label">この問題の珠の動きを見ます</div>
      <div id="learningExampleProblem" class="learning-example-problem"></div>
      <div class="learning-example-help">
        まず問題全体を見てから、下の珠がどう動くかをゆっくり追ってください。
      </div>
    </div>

    <div id="learningVideoCard" class="learning-video-card">
      <div class="learning-video-title">
        <span>珠の動き動画</span>
        <span class="learning-video-badge">自動アニメーション</span>
      </div>

      <div id="learningStepText" class="learning-step-text"></div>

      <div class="learning-soroban-wrap">
        <div id="learningSorobanBoard" class="learning-soroban-board"></div>
      </div>

      <div id="learningFrameCounter" class="learning-frame-counter"></div>

      <div class="learning-video-controls">
        <button type="button" id="learningReplayBtn">↻ もう一度</button>
        <button type="button" id="learningPauseBtn">Ⅱ 一時停止</button>
        <button type="button" id="learningVoiceBtn" class="learning-voice-btn">
          🔊 音声解説 OFF
        </button>
      </div>
      <div id="learningVoiceNote" class="learning-voice-note">
        音声解説をONにすると、珠の動きをゆっくり読み上げます。
      </div>
    </div>

    <div class="learning-explain-card">
      <div class="learning-point-grid">
        <div class="learning-point">
          <div class="learning-point-label">今回の基本</div>
          <div id="learningBasicText" class="learning-point-text"></div>
        </div>
        <div class="learning-point trouble">
          <div class="learning-point-label">つまずきやすいところ</div>
          <div id="learningTroubleText" class="learning-point-text"></div>
        </div>
      </div>

      <div id="learningRuleBox" class="learning-rule-box"></div>
    </div>

    <div class="learning-quiz-card">
      <div class="learning-video-title">
        <span>理解チェック</span>
        <span class="learning-video-badge">クリアで ★</span>
      </div>
      <div id="learningQuizQuestion" class="learning-quiz-question"></div>
      <div id="learningQuizOptions" class="learning-quiz-options"></div>
      <div id="learningQuizFeedback" class="learning-quiz-feedback"></div>

      <div id="learningClearActions" class="learning-clear-actions">
        <button type="button" id="learningAgainBtn">動画をもう一度</button>
        <button type="button" id="learningNextBtn" class="primary">次のSTEPへ</button>
      </div>
    </div>
  </div>
</div>

<div id="cameraSetupModal" class="camera-modal">
  <div class="camera-dialog">
    <h3>撮影準備｜画角を確認</h3>
    <p>
      <strong>両手とそろばん全体を下の白い枠へ。</strong>
      顔は上の小さい枠に一部入れば十分です。
    </p>

    <div class="camera-preview-wrap">
      <video
        id="analysisCameraPreview"
        class="camera-preview"
        autoplay
        muted
        playsinline
      ></video>
      <div class="camera-face-guide">
        <div class="camera-face-label">顔はこの辺り</div>
      </div>
      <div class="camera-guide">
        <div class="camera-guide-label">両手＋そろばん全体をここへ</div>
      </div>
    </div>

    <div id="cameraSetupStatus" class="camera-status">
      カメラを準備しています…
    </div>

    <div class="camera-actions">
      <button type="button" id="cameraCancelBtn">キャンセル</button>
      <button type="button" id="cameraNoVideoBtn">撮影なしで開始</button>
      <button type="button" id="cameraBeginBtn" class="primary" disabled>
        この画角で開始
      </button>
    </div>
  </div>
</div>

<section id="workspace" class="workspace">
  <div class="statusbar">
    <div>
      <div id="statusTitle" class="status-title"></div>
      <div id="statusSub" class="status-sub">12問・制限時間5分</div>
    </div>
    <div id="timer" class="timer">5:00</div>
    <div id="streak" class="streak">連続正解 0</div>
    <button type="button" id="voiceBtn" class="voice-btn">🎤 音声回答 OFF</button>
    <button type="button" id="bgmBtn">♪ BGM ON</button>
    <div id="recordingBadge" class="recording-badge">● REC</div>
    <div class="challenge-quick-nav">
      <button type="button" id="challengePlayTopBtn" data-app-nav="home" onclick="window.__sorobanHardNav && window.__sorobanHardNav('home'); return false;">← TOPへ</button>
      <button type="button" id="quitBtn" data-app-nav="challenge-menu" onclick="window.__sorobanHardNav && window.__sorobanHardNav('challenge-menu'); return false;">モード選択へ</button>
      <button type="button" id="restartChallengeBtn" class="restart-challenge-btn">↻ 最初からやり直す</button>
    </div>
    <div id="voiceStatus" class="voice-status">音声回答：OFF</div>
    <div id="bgmName" class="bgm-name">BGM：準備中</div>
  </div>

  <div id="questionCard" class="question-card">
    <div class="qtop">
      <div>
        <span id="qCount" class="qcount">1 / 12</span>
        <span id="weakBadge" class="weak-badge">にがて克服</span>
      </div>
      <div id="score" class="score">正解 0</div>
    </div>

    <div id="equation" class="equation"></div>

    <div class="hint-launch">
      <button type="button" id="hintBtn" class="hint-btn">
        珠ヒントを見る（手動＋音声）
      </button>
    </div>

    <div id="abacusHint" class="abacus-hint">
      <div class="hint-head">
        <div class="hint-title">そろばんの珠の動かし方｜1つずつ進む</div>
        <div class="hint-actions">
          <button type="button" id="hintCloseBtn">閉じる</button>
        </div>
      </div>

      <div class="soroban-scroll">
        <div id="sorobanBoard" class="soroban-board"></div>
      </div>

      <div class="hint-legend">
        薄い黄色に光る珠が、いま使っている・動かしている珠です。
      </div>

      <div class="hint-lower-panel">
        <div id="hintStep" class="hint-step"></div>
        <div id="hintVoiceStatus" class="hint-voice-status"></div>

        <div id="hintAnswerControls" class="hint-answer-controls">
          <button type="button" id="hintMicAnswerBtn" class="hint-mic-answer-btn">🎤 声で答える</button>
          <div id="hintNumberGrid" class="hint-number-grid">
            <button type="button" class="hint-number-btn" data-hint-number="1">1</button>
            <button type="button" class="hint-number-btn" data-hint-number="2">2</button>
            <button type="button" class="hint-number-btn" data-hint-number="3">3</button>
            <button type="button" class="hint-number-btn" data-hint-number="4">4</button>
            <button type="button" class="hint-number-btn" data-hint-number="5">5</button>
            <button type="button" class="hint-number-btn" data-hint-number="6">6</button>
            <button type="button" class="hint-number-btn" data-hint-number="7">7</button>
            <button type="button" class="hint-number-btn" data-hint-number="8">8</button>
            <button type="button" class="hint-number-btn" data-hint-number="9">9</button>
          </div>
        </div>

        <div class="hint-manual-nav">
          <button type="button" id="hintPrevBtn">← 戻る</button>
          <div id="hintStepCounter" class="hint-manual-counter">STEP 1 / 1</div>
          <button type="button" id="hintNextBtn" class="primary">進む →</button>
        </div>
      </div>
    </div>

    <form id="answerForm" class="answer-form">
      <input
        id="answerInput"
        class="answer-input"
        type="text"
        inputmode="none"
        autocomplete="off"
        aria-label="答え"
        placeholder="答え"
        readonly
      >
      <button type="submit" class="primary">答える</button>
    </form>

    <div class="keypad-wrap">
      <div class="keypad-label">数字をタップして入力</div>
      <div id="keypad" class="keypad">
        <button type="button" data-key="7">7</button>
        <button type="button" data-key="8">8</button>
        <button type="button" data-key="9">9</button>
        <button type="button" data-key="4">4</button>
        <button type="button" data-key="5">5</button>
        <button type="button" data-key="6">6</button>
        <button type="button" data-key="1">1</button>
        <button type="button" data-key="2">2</button>
        <button type="button" data-key="3">3</button>
        <button type="button" class="key-action" data-action="clear">クリア</button>
        <button type="button" data-key="0">0</button>
        <button type="button" class="key-action" data-action="backspace">← 1つ消す</button>
      </div>
    </div>

    <div id="feedback" class="feedback"></div>

    <div class="progress">
      <div id="bar" class="bar"></div>
    </div>
  </div>

  <div id="results" class="results">
    <div class="result-note">結果</div>

    <div id="scoreStage" class="score-stage">
      <div class="score-caption">チャレンジスコア</div>
      <div id="resultScore" class="result-score">---</div>
      <div id="scoreFormula" class="score-formula"></div>
    </div>

    <div id="resultNote" class="result-note"></div>

    <div id="resultRankingPanel" class="ranking-panel">
      <div class="ranking-panel-title">このモードの過去の得点ランキング</div>
      <div class="ranking-note">
        点数は小さめに表示しています。不要な記録は1件ずつ削除できます。
      </div>
      <div id="resultRankingList" class="ranking-list"></div>
    </div>

    <div id="videoReviewPanel" class="video-review-panel hidden">
      <div class="video-review-title">今回の課題と次の練習</div>
      <div class="video-review-note">
        正誤・回答時間・珠ヒント使用などのログから、復習する内容を短く整理します。
        動画の問題別再生は表示せず、解説と補習を優先します。
      </div>

      <div class="coaching-rank-strip">
        <div>
          <div class="coaching-rank-label">現在のアプリ内階級</div>
          <div id="resultRankTitle" class="coaching-rank-title">見習い</div>
        </div>
        <div id="resultRankProgress" class="video-question-meta"></div>
      </div>

      <div id="coachingIssueList" class="coaching-issues"></div>

      <div id="videoReviewStatus" class="camera-status">
        学習ログはこの端末内に自動保存されます。
      </div>

      <div class="video-review-actions">
        <button type="button" id="downloadSessionVideoBtn">録画動画を保存（任意）</button>
        <button type="button" id="downloadSessionLogBtn">今回のログを保存</button>
      </div>
    </div>

    <div id="review" class="review"></div>
    <div class="actions">
      <button type="button" id="retryBtn" class="primary">もう一回チャレンジ</button>
      <button type="button" id="promoteBtn" class="hidden">次のレベルへ</button>
      <button type="button" id="menuBtn" data-app-nav="challenge-menu" onclick="window.__sorobanHardNav && window.__sorobanHardNav('challenge-menu'); return false;">モード選択へ</button>
      <button type="button" id="resultTopBtn" data-app-nav="home" onclick="window.__sorobanHardNav && window.__sorobanHardNav('home'); return false;">← TOPへ</button>
    </div>
  </div>
</section>

<script>
(() => {
  const APP_VERSION = __APP_VERSION__;
  const BGM_URLS = __BGM_URLS__;

  const root = document.getElementById("soroban-app");
  const $ = (selector) => root.querySelector(selector);

  const appDiagnostics = (() => {
    const KEY = "soroban_diagnostics_v1", ENABLED = "soroban_diagnostics_enabled_v1";
    const LIMIT = 2000, MAX_BYTES = 1200000;
    const session = `${Date.now()}-${Math.random().toString(36).slice(2,9)}`;
    let enabled = true, records = [], dropped = 0, sequence = 0, pending = null, recent = null;
    let saveTimer = null, dirty = false, storageError = false, lastSnapshot = "", snapshotAt = 0;
    const now = () => performance.now();
    const clean = (text) => String(text || "").replace(/https?:\/\/[^\s)]+/g,"[URL]").slice(0,700);
    try {
      enabled = localStorage.getItem(ENABLED) !== "false";
      const saved = JSON.parse(localStorage.getItem(KEY) || "{}");
      if (Array.isArray(saved.records)) records = saved.records.slice(-LIMIT);
      dropped = Number(saved.dropped) || 0;
    } catch (error) { storageError = true; }
    function state() {
      const views = ["settingsView","kukuView","hosuView","anzanView","learningView","weaknessView","workspace","results"];
      const view = views.find(id => $("#"+id)?.classList.contains("show")) ||
        (!$("#menuView")?.classList.contains("hidden") ? "menuView" : "homeView");
      const count = view === "kukuView" ? $("#kukuQCount") : view === "hosuView" ? $("#hosuProgress") : view === "anzanView" ? $("#anzanQCount") : view === "workspace" ? $("#qCount") : null;
      return {view,question:count?.textContent?.match(/\d+\s*\/\s*\d+/)?.[0] || ""};
    }
    function status() {
      const node = $("#diagnosticsStatus");
      if (node) node.textContent = `${enabled ? "記録中" : "停止中"}｜${records.length}件${storageError ? "｜端末保存不可（出力は可能）" : ""}`;
      const button = $("#diagnosticsToggle");
      if (button) { button.textContent = enabled ? "記録を停止" : "記録を開始";button.setAttribute("aria-pressed",String(enabled)); }
    }
    function flush() {
      clearTimeout(saveTimer);saveTimer = null;
      if (!dirty) return;
      try {
        let data = JSON.stringify({version:1,dropped,records});
        while (data.length * 2 > MAX_BYTES && records.length > 1) {
          const count = Math.max(1,Math.ceil(records.length / 10));
          records.splice(0,count);dropped += count;
          data = JSON.stringify({version:1,dropped,records});
        }
        localStorage.setItem(KEY,data);storageError = false;dirty = false;
      } catch (error) {storageError = true;}
      status();
    }
    const association = () => pending?.id || (recent && now()-recent.start<10000 ? recent.id : null);
    function add(type,data = {},id = association()) {
      if (!enabled) return;
      records.push({time:new Date().toISOString(),session,app_version:APP_VERSION,type,interaction_id:id,...data});
      if (records.length > LIMIT) {dropped += records.length-LIMIT;records.splice(0,records.length-LIMIT);}
      dirty = true;
      if (!saveTimer) saveTimer = setTimeout(flush,2000);
    }
    function finish(reason) {
      if (!pending) return;
      const action = pending;pending = null;
      clearTimeout(action.quiet);clearTimeout(action.timeout);
      add("interaction_complete",{button:action.button,from:action.from,...state(),elapsed_ms:+(now()-action.start).toFixed(2),reason,
        measurement:"DOM quiet 150ms + two animation frames; estimated, not proof of visual completion"},action.id);
    }
    function settled() {
      if (!pending) return;
      const action = pending;
      clearTimeout(action.quiet);
      action.quiet = setTimeout(() => requestAnimationFrame(() => requestAnimationFrame(() => {
        if (pending === action) finish("dom_settled_estimate");
      })),150);
    }
    function begin(button) {
      if (!enabled) return;
      finish("superseded");
      const action = {id:`${session}-${++sequence}`,button,from:state().view,start:now()};pending = action;recent = action;
      add("interaction_start",{button,...state()});
      queueMicrotask(() => {
        add("handlers_returned",{elapsed_ms:+(now()-action.start).toFixed(2)},action.id);
      });
      requestAnimationFrame(() => requestAnimationFrame(() => {
        if (pending === action) add("first_frame_estimate",{elapsed_ms:+(now()-action.start).toFixed(2),...state()},action.id);
      }));
      action.timeout = setTimeout(() => {if (pending === action) finish("timeout_10s");},10000);
      settled();
    }
    function span(name,details = {}) {
      const id = association(), start = now(), on = enabled;
      if (on) add("phase_start",{name,...details},id);
      let done = false;
      return (outcome="ok") => {
        if (done) return;done = true;
        if (on) add("phase_end",{name,...details,outcome,duration_ms:+(now()-start).toFixed(2)},id);
      };
    }
    function measure(name,fn) {
      if (!enabled) return fn();
      const end=span(name);
      try {const result=fn();end();return result;} catch(error){end("error");throw error;}
    }
    function summary() {
      const groups = {};
      for (const record of records) if (record.type === "interaction_complete" && record.reason === "dom_settled_estimate") {
        const key = `${record.from} / ${record.button}`;(groups[key] ||= []).push(record.elapsed_ms);
      }
      return Object.entries(groups).map(([action,times]) => {
        times.sort((a,b)=>a-b);
        return {action,count:times.length,average_ms:+(times.reduce((a,b)=>a+b,0)/times.length).toFixed(2),p95_ms:times[Math.ceil(times.length*.95)-1],max_ms:times.at(-1)};
      }).sort((a,b)=>b.p95_ms-a.p95_ms);
    }
    function download(format) {
      flush();
      const environment = {user_agent:navigator.userAgent,language:navigator.language,width:window.innerWidth,height:window.innerHeight,pixel_ratio:window.devicePixelRatio,
        hardware_concurrency:navigator.hardwareConcurrency,device_memory_gb:navigator.deviceMemory,visibility:document.visibilityState};
      const report = {schema_version:1,exported_at:new Date().toISOString(),app_version:APP_VERSION,environment,dropped_records:dropped,
        notes:["Times are milliseconds. Visual completion is estimated from DOM quiet and animation frames.","Background tabs, speech and network waits must be assessed separately.","No microphone audio, transcripts, typed answers, or resource URLs are recorded.","Browser diagnostics start after the embedded script runs; Python startup and database latency are not directly measured."],summary:summary(),records};
      const csvCell = value => '"'+String(value ?? "").replace(/"/g,'""')+'"';
      const keys=["time","session","app_version","interaction_id","type","button","from","view","question","name","elapsed_ms","duration_ms","reason","outcome","details"];
      const body = format === "csv" ? "\uFEFF" + [keys.join(","),...records.map(r=>keys.map(k=>csvCell(k==="details"?JSON.stringify(r):r[k])).join(","))].join("\r\n") : JSON.stringify(report,null,2);
      const url=URL.createObjectURL(new Blob([body],{type:format === "csv"?"text/csv;charset=utf-8":"application/json"}));
      const link=document.createElement("a");link.href=url;link.download=`soroban_diagnostics_${new Date().toISOString().replace(/[:.]/g,"-")}.${format}`;
      document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
    }
    document.addEventListener("click",event=>{
      const button=event.target.closest?.("button,summary");
      if (!button || !root.contains(button) || button.closest("#diagnosticsPanel")) return;
      // 数字の回答は保存せず、どの入力手段を使ったかだけ記録する。
      const keypad=button.closest(".keypad,.kuku-keypad,.anzan-keypad,.hosu-digits,.hint-number-grid");
      begin(keypad?`${keypad.id || keypad.className}:key`:clean(button.id || button.textContent.trim()).slice(0,100));
    },true);
    document.addEventListener("submit",event=>{if(root.contains(event.target)&&!pending)begin("form_submit");},true);
    if (typeof MutationObserver !== "undefined") new MutationObserver(changes=>{
      if (!enabled || !changes.some(change=>!$("#diagnosticsPanel").contains(change.target))) return;
      if (pending) settled();
      if (now()-snapshotAt<250) return;snapshotAt=now();
      const current=state(),signature=JSON.stringify(current);
      if (signature!==lastSnapshot){lastSnapshot=signature;add("screen_state",{...current,action_elapsed_ms:recent?+(now()-recent.start).toFixed(2):null});}
    }).observe(root,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:["class"]});
    if (typeof PerformanceObserver !== "undefined") for (const type of ["longtask","resource"]) {
      try {new PerformanceObserver(list=>{
        for (const entry of list.getEntries()) {
          if (type === "resource" && entry.duration<100) continue;
          add(type,{duration_ms:+entry.duration.toFixed(2),start_ms:+entry.startTime.toFixed(2),
            ...(type==="resource"?{initiator:entry.initiatorType,transfer_bytes:entry.transferSize}:{}),...state()});
        }
      }).observe({type,buffered:true});} catch(error) {}
    }
    let tick=now();
    setInterval(()=>{const current=now(),lag=current-tick-1000;tick=current;
      if (enabled && document.visibilityState!=="hidden" && lag>100) add("event_loop_delay",{duration_ms:+lag.toFixed(2),...state()});
    },1000);
    window.addEventListener("error",event=>add("error",{message:clean(event.message),line:event.lineno,column:event.colno,...state()}));
    window.addEventListener("unhandledrejection",event=>add("unhandled_rejection",{message:clean(event.reason?.message || event.reason),...state()}));
    document.addEventListener("visibilitychange",()=>{add("visibility",{state:document.visibilityState});if(document.visibilityState==="hidden")flush();});
    window.addEventListener("pagehide",flush);
    $("#diagnosticsToggle").addEventListener("click",()=>{
      if (enabled) finish("recording_stopped");enabled=!enabled;
      try{localStorage.setItem(ENABLED,String(enabled));}catch(error){storageError=true;}
      add("recording_started",state());flush();status();
    });
    $("#diagnosticsJson").addEventListener("click",()=>download("json"));
    $("#diagnosticsCsv").addEventListener("click",()=>download("csv"));
    $("#diagnosticsClear").addEventListener("click",()=>{
      if(pending){clearTimeout(pending.quiet);clearTimeout(pending.timeout);pending=null;}
      records=[];dropped=0;dirty=true;flush();status();
    });
    add("session_start",{...state(),time_origin:performance.timeOrigin || null});status();
    function observeRecognition(recognition) {
      if (!recognition.addEventListener) return;
      let end = null;
      recognition.addEventListener("start",()=>{end=span("microphone_session");add("microphone_started",state());});
      recognition.addEventListener("result",()=>add("microphone_result_received",state()));
      recognition.addEventListener("error",event=>{add("microphone_error",{code:event.error,...state()});if(end)end(event.error);});
      recognition.addEventListener("end",()=>{if(end)end();});
    }
    return {span,measure,flush,observeRecognition};
  })();


  const APP_VOLUME_STORAGE_KEY = "soroban_master_volume_v1";
  let appMasterVolume = 1;
  try {
    const saved = localStorage.getItem(APP_VOLUME_STORAGE_KEY);
    const number = saved === null || saved.trim() === "" ? NaN : Number(saved);
    if (Number.isFinite(number) && number >= 0 && number <= 1) appMasterVolume = number;
  } catch (error) {}
  const appAudioOutputs = new Set();
  const appSpeechQueue = new Set();

  function connectAppAudioOutput(context, source) {
    const output = context.createGain();
    output.gain.value = appMasterVolume;
    source.connect(output);
    output.connect(context.destination);
    const entry = { context, output };
    appAudioOutputs.add(entry);
    return entry;
  }

  function releaseAppAudioOutput(entry) {
    if (!entry) return;
    appAudioOutputs.delete(entry);
    try { entry.output.disconnect(); } catch (error) {}
  }

  function speakWithAppVolume(utterance) {
    utterance.volume = appMasterVolume;
    appSpeechQueue.add(utterance);
    const onEnd = utterance.onend;
    const onError = utterance.onerror;
    const onStart = utterance.onstart;
    const queued = appDiagnostics.span("speech_queue", {characters:utterance.text?.length || 0});
    let playback = null;
    const finish = outcome => {queued(outcome);if(playback)playback(outcome);};
    utterance.__diagnosticsEnd = finish;
    utterance.onstart = function(event) {
      queued();playback = appDiagnostics.span("speech_playback");
      if (typeof onStart === "function") onStart.call(this,event);
    };
    utterance.onend = function(event) {
      appSpeechQueue.delete(utterance);
      finish("ok");
      if (typeof onEnd === "function") onEnd.call(this, event);
    };
    utterance.onerror = function(event) {
      appSpeechQueue.delete(utterance);
      finish(event?.error || "error");
      if (typeof onError === "function") onError.call(this, event);
    };
    try { window.speechSynthesis.speak(utterance); }
    catch (error) { appSpeechQueue.delete(utterance); finish("error"); throw error; }
  }

  function cancelAppSpeech() {
    appSpeechQueue.forEach(utterance => utterance.__diagnosticsEnd?.("cancelled"));
    appSpeechQueue.clear();
    window.speechSynthesis.cancel();
  }

  function setAppMasterVolume(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return;
    appMasterVolume = Math.max(0, Math.min(1, number));
    const percent = Math.round(appMasterVolume * 100);
    $("#appVolumeSlider").value = String(percent);
    $("#appVolumeSlider").setAttribute("aria-valuetext", `${percent}%`);
    $("#appVolumeValue").textContent = `${percent}%`;
    for (const entry of appAudioOutputs) {
      if (entry.context.state === "closed") { appAudioOutputs.delete(entry); continue; }
      try {
        const now = entry.context.currentTime;
        const gain = entry.output.gain;
        gain.cancelScheduledValues(now);
        gain.setValueAtTime(gain.value, now);
        gain.linearRampToValueAtTime(appMasterVolume, now + 0.03);
      } catch (error) {}
    }
    // 再生中・待機中の発話にも反映。発話の中断や再回答は発生させない。
    for (const utterance of appSpeechQueue) utterance.volume = appMasterVolume;
    try { localStorage.setItem(APP_VOLUME_STORAGE_KEY, String(appMasterVolume)); } catch (error) {}
  }

  $("#appVolumeSlider").addEventListener("input", (event) => {
    setAppMasterVolume(Number(event.target.value) / 100);
  });
  $("#appVolumeSlider").value = String(Math.round(appMasterVolume * 100));
  $("#appVolumeSlider").setAttribute("aria-valuetext", `${Math.round(appMasterVolume * 100)}%`);
  $("#appVolumeValue").textContent = `${Math.round(appMasterVolume * 100)}%`;


  window.addEventListener(
    "error",
    (event) => {
      try {
        root.dataset.runtimeError =
          String(event.message || "runtime error");
      } catch (error) {}
    }
  );

  // Navigation is deliberately dependency-free and installed before all other app logic.
  // It changes only view classes using raw DOM queries, so even a later JS error cannot trap the user.
  function hardSetView(...args) {
    return appDiagnostics.measure("hardSetView", () => hardSetViewMeasured.apply(this,args));
  }
  function hardSetViewMeasured(target) {
    try { stopKukuTableReading(); } catch (error) {}
    try { stopHosuSession(); } catch (error) {}
    root.querySelector("#hosuView")?.classList.remove("show");
    const byId = (id) => root.querySelector(`#${id}`);
    const home = byId("homeView");
    const menu = byId("menuView");
    const learning = byId("learningView");
    const anzan = byId("anzanView");
    const settings = byId("settingsView");
    const weakness = byId("weaknessView");
    const kuku = byId("kukuView");
    const workspaceEl = byId("workspace");
    const resultsEl = byId("results");

    if (!home || !menu || !learning || !anzan || !settings || !weakness || !kuku || !workspaceEl || !resultsEl) {
      return false;
    }

    const hideEverything = () => {
      home.classList.add("hidden");
      menu.classList.add("hidden");
      learning.classList.remove("show");
      anzan.classList.remove("show");
      settings.classList.remove("show");
      weakness.classList.remove("show");
      kuku.classList.remove("show");
      workspaceEl.classList.remove("show");
      resultsEl.classList.remove("show");
    };

    hideEverything();

    if (target === "home") {
      home.classList.remove("hidden");
    } else if (target === "challenge" || target === "challenge-menu") {
      menu.classList.remove("hidden");
    } else if (target === "learning") {
      weakness.classList.add("show");
    } else if (target === "anzan") {
      anzan.classList.add("show");
      const menuViewEl = byId("anzanMenuView");
      const gameViewEl = byId("anzanGameView");
      const resultViewEl = byId("anzanResultView");
      if (menuViewEl) menuViewEl.classList.remove("hidden");
      if (gameViewEl) gameViewEl.classList.add("hidden");
      if (resultViewEl) resultViewEl.classList.add("hidden");
    } else if (target === "settings") {
      settings.classList.add("show");
    } else if (target === "weakness") {
      weakness.classList.add("show");
    } else if (target === "hosu") {
      byId("hosuView")?.classList.add("show");
    } else if (target === "kuku") {
      kuku.classList.add("show");
      const menuViewEl = byId("kukuMenuView");
      const gameViewEl = byId("kukuGameView");
      const resultViewEl = byId("kukuResultView");
      if (menuViewEl) menuViewEl.classList.remove("hidden");
      if (gameViewEl) gameViewEl.classList.add("hidden");
      if (resultViewEl) resultViewEl.classList.add("hidden");
    } else {
      return false;
    }

    return true;
  }

  let lastHardNavAt = 0;
  let lastHardNavTarget = "";

  function hardNavigate(target) {
    learningInterrupt();
    const now = Date.now();
    if (target === lastHardNavTarget && now - lastHardNavAt < 450) {
      return;
    }

    lastHardNavAt = now;
    lastHardNavTarget = target;

    // TOP／モード選択へ明示的に戻った場合は、
    // 「アプリを閉じた」ケースではないため再開データを残さない。
    try {
      const workspaceEl =
        root.querySelector(
          "#workspace"
        );
      const resultsEl =
        root.querySelector(
          "#results"
        );

      if (
        (
          target === "home" ||
          target === "challenge-menu" ||
          target === "weakness" ||
          target === "kuku" ||
          target === "hosu"
        ) &&
        workspaceEl?.classList.contains(
          "show"
        ) &&
        !resultsEl?.classList.contains(
          "show"
        ) &&
        typeof clearChallengeResumeState ===
          "function"
      ) {
        clearChallengeResumeState();
      }
    } catch (error) {}

    hardSetView(target);

    // Cleanup is secondary. The view has already changed even if cleanup fails.
    setTimeout(() => {
      try {
        if (target === "home") showHome();
        else if (target === "challenge-menu") goMenu();
        else if (target === "challenge") showChallengeMenu();
        else if (target === "learning") showWeaknessHome();
        else if (target === "anzan") showAnzanHome();
        else if (target === "settings") showSettings();
        else if (target === "weakness") showWeaknessHome();
        else if (target === "kuku") showKukuHome();
        else if (target === "hosu") showHosuHome();
      } catch (error) {}
    }, 0);
  }

  window.__sorobanHardNav = hardNavigate;

  function handleHardNavEvent(event) {
    const button = event.target.closest("[data-app-nav]");
    if (!button || !root.contains(button)) return;

    event.preventDefault();
    event.stopPropagation();

    hardNavigate(button.dataset.appNav);
  }

  // pointerup is primary on phones; click is a fallback for keyboard/mouse/browser quirks.
  root.addEventListener("pointerup", handleHardNavEvent, true);
  root.addEventListener("click", handleHardNavEvent, true);

  $("#versionLabel").textContent = `APP VERSION: ${APP_VERSION}`;

  const homeView = $("#homeView");
  const anzanView = $("#anzanView");
  const anzanMenuView = $("#anzanMenuView");
  const anzanGameView = $("#anzanGameView");
  const anzanResultView = $("#anzanResultView");
  const settingsView = $("#settingsView");
  const weaknessView = $("#weaknessView");
  const kukuView = $("#kukuView");
  const kukuMenuView = $("#kukuMenuView");
  const kukuGameView = $("#kukuGameView");
  const kukuResultView = $("#kukuResultView");
  const kukuQCount = $("#kukuQCount");
  const kukuTimer = $("#kukuTimer");
  const kukuCorrectCount = $("#kukuCorrectCount");
  const kukuEquation = $("#kukuEquation");
  const kukuPrompt = $("#kukuPrompt");
  const kukuVoiceBtn = $("#kukuVoiceBtn");
  const kukuAnswerDisplay = $("#kukuAnswerDisplay");
  const kukuFeedback = $("#kukuFeedback");
  const kukuResultScore = $("#kukuResultScore");
  const kukuResultText = $("#kukuResultText");
  const menuView = $("#menuView");
  const learningView = $("#learningView");
  const learningCategoryView = $("#learningCategoryView");
  const learningStageView = $("#learningStageView");
  const learningLessonView = $("#learningLessonView");
  const learningCategoryGrid = $("#learningCategoryGrid");
  const learningStageGrid = $("#learningStageGrid");
  const learningOverallText = $("#learningOverallText");
  const learningOverallBar = $("#learningOverallBar");
  const learningStageKicker = $("#learningStageKicker");
  const learningStageHeading = $("#learningStageHeading");
  const learningLessonKicker = $("#learningLessonKicker");
  const learningLessonTitle = $("#learningLessonTitle");
  const learningExampleProblem = $("#learningExampleProblem");
  const learningVideoCard = $("#learningVideoCard");
  const learningStepText = $("#learningStepText");
  const learningSorobanBoard = $("#learningSorobanBoard");
  const learningFrameCounter = $("#learningFrameCounter");
  const learningBasicText = $("#learningBasicText");
  const learningTroubleText = $("#learningTroubleText");
  const learningRuleBox = $("#learningRuleBox");
  const learningQuizQuestion = $("#learningQuizQuestion");
  const learningQuizOptions = $("#learningQuizOptions");
  const learningQuizFeedback = $("#learningQuizFeedback");
  const learningClearActions = $("#learningClearActions");
  const learningPauseBtn = $("#learningPauseBtn");
  const learningVoiceBtn = $("#learningVoiceBtn");
  const learningVoiceNote = $("#learningVoiceNote");
  const learningNextBtn = $("#learningNextBtn");

  const anzanFlash = $("#anzanFlash");
  const anzanHint = $("#anzanHint");
  const anzanAnswerArea = $("#anzanAnswerArea");
  const anzanAnswerDisplay = $("#anzanAnswerDisplay");
  const anzanFeedback = $("#anzanFeedback");
  const anzanVoiceStatus = $("#anzanVoiceStatus");
  const anzanQCount = $("#anzanQCount");
  const anzanCorrectCount = $("#anzanCorrectCount");
  const anzanSpeedLabel = $("#anzanSpeedLabel");
  const anzanResultScore = $("#anzanResultScore");
  const anzanResultText = $("#anzanResultText");

  const settingTimeValue = $("#settingTimeValue");
  const settingVoiceValue = $("#settingVoiceValue");
  const settingBgmValue = $("#settingBgmValue");
  const settingLearningVoiceValue = $("#settingLearningVoiceValue");
  const settingAnzanSpeedValue = $("#settingAnzanSpeedValue");
  const appRankBadge = $("#appRankBadge");
  const appRankMeterFill = $("#appRankMeterFill");
  const appRankSub = $("#appRankSub");
  const appRankNext = $("#appRankNext");
  const homeAddSubMedal = $("#homeAddSubMedal");
  const homeAddSubRankName = $("#homeAddSubRankName");
  const homeAddSubRankNext = $("#homeAddSubRankNext");
  const homeMulDivMedal = $("#homeMulDivMedal");
  const homeMulDivRankName = $("#homeMulDivRankName");
  const homeMulDivRankNext = $("#homeMulDivRankNext");
  const medalCollectionGrid = $("#medalCollectionGrid");
  const medalConditionList = $("#medalConditionList");
  const medalResetBtn = $("#medalResetBtn");
  const medalResetStatus = $("#medalResetStatus");
  const rankCelebration = $("#rankCelebration");
  const rankConfettiLayer = $("#rankConfettiLayer");
  const rankCelebrationMedal = $("#rankCelebrationMedal");
  const rankCelebrationMedalText = $("#rankCelebrationMedalText");
  const rankCelebrationTitle = $("#rankCelebrationTitle");
  const rankCelebrationSub = $("#rankCelebrationSub");

  const workspace = $("#workspace");
  const questionCard = $("#questionCard");
  const results = $("#results");
  const equation = $("#equation");
  const answerInput = $("#answerInput");
  const feedback = $("#feedback");
  const timerEl = $("#timer");
  const statusSub = $("#statusSub");
  const timeLimitBtn = $("#timeLimitBtn");
  const modeTimeBadge = $("#modeTimeBadge");
  const challengeResumeCard = $("#challengeResumeCard");
  const challengeResumeText = $("#challengeResumeText");
  const resumeChallengeBtn = $("#resumeChallengeBtn");
  const discardResumeBtn = $("#discardResumeBtn");
  const nextRankGuide = $("#nextRankGuide");
  const nextRankGuideTitle = $("#nextRankGuideTitle");
  const nextRankGuideText = $("#nextRankGuideText");
  const weaknessChallengeGrid = $("#weaknessChallengeGrid");
  const promoteBtn = $("#promoteBtn");
  const analysisVideoToggle = $("#analysisVideoToggle");
  const cameraSetupModal = $("#cameraSetupModal");
  const analysisCameraPreview = $("#analysisCameraPreview");
  const cameraSetupStatus = $("#cameraSetupStatus");
  const cameraBeginBtn = $("#cameraBeginBtn");
  const recordingBadge = $("#recordingBadge");
  const bar = $("#bar");
  const scoreStage = $("#scoreStage");
  const resultScore = $("#resultScore");
  const scoreFormula = $("#scoreFormula");
  const resultRankingList = $("#resultRankingList");
  const resultRankingPanel = $("#resultRankingPanel");
  const videoReviewPanel = $("#videoReviewPanel");
  const videoReviewStatus = $("#videoReviewStatus");
  const coachingIssueList = $("#coachingIssueList");
  const resultRankTitle = $("#resultRankTitle");
  const resultRankProgress = $("#resultRankProgress");
  const rankingModal = $("#rankingModal");
  const rankingModalTitle = $("#rankingModalTitle");
  const rankingModalList = $("#rankingModalList");

  const voiceBtn = $("#voiceBtn");
  const voiceStatus = $("#voiceStatus");
  const bgmBtn = $("#bgmBtn");
  const bgmName = $("#bgmName");
  const hintBtn = $("#hintBtn");
  const hintPrevBtn = $("#hintPrevBtn");
  const hintNextBtn = $("#hintNextBtn");
  const hintStepCounter = $("#hintStepCounter");
  const abacusHint = $("#abacusHint");
  const hintStep = $("#hintStep");
  const hintVoiceStatus = $("#hintVoiceStatus");
  const hintAnswerControls = $("#hintAnswerControls");
  const hintMicAnswerBtn = $("#hintMicAnswerBtn");
  const hintNumberGrid = $("#hintNumberGrid");
  const sorobanBoard = $("#sorobanBoard");

  // TOPの4ボタンは、メダル・ログ・カメラなどの初期化より先に独立して登録する。
  // 追加機能側で例外が起きても、TOPから各モードへ移動できるようにする。
  // Primary navigation is handled by the delegated data-app-nav listener.

  const modeInfo = {
    ba1: { title: "初級・足し算1｜1桁・繰り上がりなし" },
    ba2: { title: "初級・足し算2｜1桁・繰り上がりあり" },
    ba2x4: { title: "初級・足し算3｜1桁の数を4つ足す" },
    ba3: { title: "初級・足し算4｜2桁・繰り上がりなし" },
    ba4: { title: "初級・足し算5｜2桁・繰り上がりあり" },
    ba4x4: { title: "初級・足し算6｜2桁の数を4つ足す" },
    ba5: { title: "初級・足し算7｜3桁の足し算" },
    ba5x4: { title: "初級・足し算8｜3桁の数を4つ足す" },
    bs1: { title: "初級・引き算1｜1桁・繰り下がりなし" },
    bs2: { title: "初級・引き算2｜1桁を引く・繰り下がりあり" },
    bs2x4: { title: "初級・引き算3｜2桁から1桁の数を3回引く" },
    bs3: { title: "初級・引き算4｜2桁・繰り下がりなし" },
    bs4: { title: "初級・引き算5｜2桁・繰り下がりあり" },
    bs4x4: { title: "初級・引き算6｜2桁の数を4つ使う引き算" },
    bs5: { title: "初級・引き算7｜3桁の引き算" },
    bs5x4: { title: "初級・引き算8｜3桁から2桁を4回引く" },
    mm1: { title: "中級・掛け算1｜1桁×1桁" },
    mm2: { title: "中級・掛け算2｜2桁×1桁" },
    mm3: { title: "中級・掛け算3｜2桁×2桁" },
    md1: { title: "中級・割り算1｜1〜81÷1桁" },
    md2: { title: "中級・割り算2｜3桁÷1桁" },
    md3: { title: "中級・割り算3｜3桁÷2桁" },
    a1: { title: "上級1｜4桁の足し算・引き算" },
    a2: { title: "上級2｜3桁×2桁 / 4桁÷2桁" },
    a3: { title: "上級3｜3桁×3桁 / 5桁÷3桁" }
  };

  const MODE_GROUPS = Object.freeze([
    { key: "add", title: "足し算", modes: ["ba1", "ba2", "ba2x4", "ba3", "ba4", "ba4x4", "ba5", "ba5x4"] },
    { key: "sub", title: "引き算", modes: ["bs1", "bs2", "bs2x4", "bs3", "bs4", "bs4x4", "bs5", "bs5x4"] },
    { key: "mul", title: "掛け算", modes: ["mm1", "mm2", "mm3"] },
    { key: "div", title: "割り算", modes: ["md1", "md2", "md3"] },
    { key: "advanced", title: "上級総合", modes: ["a1", "a2", "a3"] }
  ]);

  function operationLabelForMode(mode) {
    if (String(mode).startsWith("ba")) return "足し算";
    if (String(mode).startsWith("bs")) return "引き算";
    if (String(mode).startsWith("mm")) return "掛け算";
    if (String(mode).startsWith("md")) return "割り算";
    if (mode === "a1") return "足・引";
    if (mode === "a2" || mode === "a3") return "掛・割";
    return "総合";
  }

  const LEARNING_PROGRESS_STORAGE_KEY =
    "soroban_tutorial_progress_v1";

  const learningCategories = {
    add: {
      symbol: "＋",
      title: "足し算",
      desc: "一珠・五珠から、5の補数、10の補数、2桁の繰り上がりへ進みます。",
      lessons: [
        {
          id: "add1",
          example: "2 ＋ 2 ＝ ?",
          title: "1〜4をそのまま足す",
          desc: "使える一珠を、そのまま梁へ寄せる基本。",
          basic: "足したい数だけ一珠が残っているときは、同じ位の一珠を梁へ寄せます。まずは珠を数えず、形で1〜4を見分けることが大切です。",
          trouble: "指で珠を1個ずつ数え続けると速くなりません。『2の形』『3の形』を一目で見る練習をします。",
          rule: "足せる珠がある → そのまま足す。",
          frames: [
            { value: 2, place: 1, text: "まず 2 を置きます。" },
            { value: 3, place: 1, text: "＋2 の1個目。1の珠を1つ梁へ寄せます。" },
            { value: 4, place: 1, text: "＋2 の2個目。もう1つ寄せて 4 です。" }
          ],
          quiz: { q: "2 ＋ 2 の答えは？", options: ["3", "4", "5"], answer: "4" }
        },
        {
          id: "add2",
          example: "5 ＋ 3 ＝ ?",
          title: "5珠と1珠を組み合わせる",
          desc: "5〜9の形をすばやく作る。",
          basic: "5は上の五珠を梁へ寄せます。6〜9は『5＋一珠』の形です。たとえば8は、五珠1つと一珠3つです。",
          trouble: "6〜9を一珠6個のように考えないこと。『5といくつ』で見ると珠の形が安定します。",
          rule: "6〜9は『5 ＋ 1〜4』で見る。",
          frames: [
            { value: 5, place: 1, text: "まず 5。上の五珠を梁へ寄せます。" },
            { value: 6, place: 1, text: "＋3 の1個目。一珠を1つ寄せます。" },
            { value: 7, place: 1, text: "2個目を寄せます。" },
            { value: 8, place: 1, text: "3個目を寄せて 8 です。" }
          ],
          quiz: { q: "そろばんの 8 は『5 ＋ いくつ』？", options: ["2", "3", "4"], answer: "3" }
        },
        {
          id: "add3",
          example: "2 ＋ 4 ＝ ?",
          title: "5の補数で足す",
          desc: "一珠が足りないときに『＋5 − 補数』を使う。",
          basic: "同じ位で一珠が足りないときは、先に5の補数を引いてから5を足します。2＋4なら、4の5に対する補数は1なので『−1 → ＋5』です。",
          trouble: "『何を引くか』を毎回数えないこと。1と4、2と3を5の組として覚えます。",
          rule: "＋4 は「−1 → ＋5」／ ＋3 は「−2 → ＋5」の順。",
          frames: [
            { value: 2, place: 1, text: "2 ＋ 4。2を置きます。" },
            { value: 1, place: 1, text: "4をそのまま足せないので、先に補数の −1。2 → 1。" },
            { value: 6, place: 1, text: "そのあと ＋5。答えは 6。" }
          ],
          quiz: { q: "2 ＋ 4 では、最初にどの珠を動かす？", options: ["−1", "＋5", "＋10"], answer: "−1" }
        },
        {
          id: "add4",
          example: "8 ＋ 7 ＝ ?",
          title: "10の補数で繰り上がる",
          desc: "9を超えるときに『＋10 − 補数』を使う。",
          basic: "一の位で9を超えるときは、先に一の位から10の補数を引き、そのあと十の位へ1を足します。8＋7なら、先に−3、そのあと＋10です。",
          trouble: "順番を逆にしないこと。『一の位から補数を引く → 十の位を1上げる』の順に固定します。",
          rule: "＋7 は「−3 → ＋10」／ ＋8 は「−2 → ＋10」／ ＋9 は「−1 → ＋10」の順。",
          frames: [
            { value: 8, place: 1, text: "8 ＋ 7。まず8を置きます。" },
            { value: 5, place: 1, text: "10をまたぐので、先に7の補数3を一の位から −3。8 → 5。" },
            { value: 15, place: 10, text: "そのあと十の位へ ＋10。答えは15。" }
          ],
          quiz: { q: "8 ＋ 7 で使う10の補数は？", options: ["2", "3", "4"], answer: "3" }
        },
        {
          id: "add5",
          example: "36 ＋ 27 ＝ ?",
          title: "2桁の繰り上がり",
          desc: "十の位と一の位を分けて処理する。",
          basic: "2桁は大きい位から足します。36＋27なら、まず＋20で56。そのあと一の位の＋7は『−3 → ＋10』の順で処理します。",
          trouble: "20と7を一度に処理しようとしないこと。『十の位 → 一の位』と分けると、どこで繰り上がったかが見えます。",
          rule: "2桁は位ごとに分解。大きい位から順番に。",
          frames: [
            { value: 36, place: null, text: "36 ＋ 27。まず36を置きます。" },
            { value: 56, place: 10, text: "27の十の位、＋20。36 → 56。" },
            { value: 53, place: 1, text: "一の位の＋7は10をまたぐので、先に補数3を −3。56 → 53。" },
            { value: 63, place: 10, text: "そのあと ＋10。答えは63。" }
          ],
          quiz: { q: "36 ＋ 27 で最初に足すのは？", options: ["7", "20", "27全部"], answer: "20" }
        }
      ]
    },
    sub: {
      symbol: "－",
      title: "引き算",
      desc: "そのまま引くところから、5の補数、10の補数、2桁の繰り下がりへ。",
      lessons: [
        {
          id: "sub1",
          example: "4 － 2 ＝ ?",
          title: "そのまま引く",
          desc: "取れる一珠があるときは直接梁から離す。",
          basic: "引きたい数だけ一珠が梁に寄っているときは、その珠を梁から離します。",
          trouble: "答えの珠を新しく作るのではなく、『今ある珠から取る』と考えます。",
          rule: "取れる珠がある → そのまま引く。",
          frames: [
            { value: 4, place: 1, text: "4 − 2。まず4を置きます。" },
            { value: 3, place: 1, text: "一珠を1つ梁から離します。" },
            { value: 2, place: 1, text: "もう1つ離して、答えは2。" }
          ],
          quiz: { q: "4 − 2 の答えは？", options: ["1", "2", "3"], answer: "2" }
        },
        {
          id: "sub2",
          example: "8 － 3 ＝ ?",
          title: "5珠から直接引く",
          desc: "8−3など、五珠を残して一珠を取る。",
          basic: "8は5＋3です。8−3なら、一珠3つをそのまま梁から離せば5が残ります。",
          trouble: "五珠まで動かしてしまわないこと。まず『取れる一珠が何個あるか』を見ます。",
          rule: "8 −3 → 一珠3つをそのまま取る。",
          frames: [
            { value: 8, place: 1, text: "8は『5＋3』の形です。" },
            { value: 7, place: 1, text: "一珠を1つ取ります。" },
            { value: 6, place: 1, text: "2つ目を取ります。" },
            { value: 5, place: 1, text: "3つ目を取って5。" }
          ],
          quiz: { q: "8 − 3 では、最初にどの珠を見る？", options: ["一珠", "十の位", "全部動かす"], answer: "一珠" }
        },
        {
          id: "sub3",
          example: "7 － 4 ＝ ?",
          title: "5の補数で引く",
          desc: "一珠だけでは引けないときに『−5＋補数』。",
          basic: "7−4では、一珠は2個しかないため4を直接取れません。そこで−5して、4の5に対する補数1を＋1します。",
          trouble: "『−5したから終わり』ではありません。必ず補数を戻します。",
          rule: "−4 ＝ −5 ＋1 ／ −3 ＝ −5 ＋2。",
          frames: [
            { value: 7, place: 1, text: "7 − 4。7を置きます。" },
            { value: 2, place: 1, text: "4を直接取れないので、まず −5。7 → 2。" },
            { value: 3, place: 1, text: "4の補数1を ＋1。答えは3。" }
          ],
          quiz: { q: "7 − 4 の珠の動きは？", options: ["−5＋1", "−5＋2", "−10＋4"], answer: "−5＋1" }
        },
        {
          id: "sub4",
          example: "12 － 7 ＝ ?",
          title: "10の補数で繰り下がる",
          desc: "一の位だけでは引けないときに『−10＋補数』。",
          basic: "12−7では一の位の2から7を引けません。十の位から1を下げて−10し、一の位へ7の10の補数3を足します。",
          trouble: "『借りた10』を頭の中だけで処理しないこと。十の位の珠を実際に1つ下げる動きを先にします。",
          rule: "−7 ＝ −10 ＋3 ／ −8 ＝ −10 ＋2 ／ −9 ＝ −10 ＋1。",
          frames: [
            { value: 12, place: 1, text: "12 − 7。まず12を置きます。" },
            { value: 2, place: 10, text: "一の位だけでは引けないので、十の位から −10。" },
            { value: 5, place: 1, text: "7の補数3を一の位へ ＋3。答えは5。" }
          ],
          quiz: { q: "12 − 7 で足し戻す数は？", options: ["2", "3", "7"], answer: "3" }
        },
        {
          id: "sub5",
          example: "43 － 28 ＝ ?",
          title: "2桁の繰り下がり",
          desc: "43−28を位ごとに処理する。",
          basic: "43−28なら、まず−20で23。そのあと−8は一の位だけでは引けないので『−10＋2』にします。",
          trouble: "28を一気に引かないこと。十の位20と一の位8を分ければ、補数を使う場所が明確になります。",
          rule: "2桁の引き算も、大きい位から順番に。",
          frames: [
            { value: 43, place: null, text: "43 − 28。まず43を置きます。" },
            { value: 23, place: 10, text: "十の位の −20。43 → 23。" },
            { value: 13, place: 10, text: "一の位の−8は直接できないので、まず −10。" },
            { value: 15, place: 1, text: "8の補数2を ＋2。答えは15。" }
          ],
          quiz: { q: "43 − 28 で最初に引くのは？", options: ["8", "20", "28全部"], answer: "20" }
        }
      ]
    },
    mul: {
      symbol: "×",
      title: "掛け算",
      desc: "九九→部分積→位取り。答えをどの位の珠へ置くかを段階的に学びます。",
      lessons: [
        {
          id: "mul1",
          example: "3 × 4 ＝ ?",
          title: "九九の答えを珠に置く",
          desc: "3×4＝12を十の位・一の位に置く。",
          basic: "掛け算ではまず九九で答えを作ります。12なら十の位に1、一の位に2を置きます。",
          trouble: "『12』を一の位に12個置こうとしないこと。必ず十の位1、一の位2に分けます。",
          rule: "九九の答えも、位に分けて珠へ置く。",
          frames: [
            { value: 0, place: null, text: "3 × 4。九九で答えは12です。" },
            { value: 10, place: 10, text: "12の十の位、1を置きます。" },
            { value: 12, place: 1, text: "一の位に2を置いて12。" }
          ],
          quiz: { q: "3 × 4 の答え12。十の位に置く数は？", options: ["1", "2", "12"], answer: "1" }
        },
        {
          id: "mul2",
          example: "23 × 4 ＝ ?",
          title: "2桁×1桁の部分積",
          desc: "23×4を20×4と3×4に分ける。",
          basic: "23×4は『20×4＝80』と『3×4＝12』に分けます。部分積を位をそろえて足すと92です。",
          trouble: "2×4＝8を『8』として一の位へ置かないこと。2は十の位なので、20×4＝80です。",
          rule: "元の数字の位を、掛けた後も忘れない。",
          frames: [
            { value: 0, place: null, text: "23 × 4。まず20×4を考えます。" },
            { value: 80, place: 10, text: "20 × 4 ＝ 80。80を置きます。" },
            { value: 90, place: 10, text: "次に3×4＝12。まず十の位の10を加えます。" },
            { value: 92, place: 1, text: "一の位の2を加えて92。" }
          ],
          quiz: { q: "23 × 4 で、20 × 4 は？", options: ["8", "80", "800"], answer: "80" }
        },
        {
          id: "mul3",
          example: "24 × 13 ＝ ?",
          title: "2桁×2桁",
          desc: "24×13を×10と×3に分ける。",
          basic: "24×13は、24×10＝240と24×3＝72に分けます。240＋72＝312です。",
          trouble: "13を『1と3』として同じ位に扱わないこと。1は十の位なので×10です。",
          rule: "2桁の掛ける数は『十の位の部分積＋一の位の部分積』。",
          frames: [
            { value: 0, place: null, text: "24 × 13。13を10と3に分けます。" },
            { value: 240, place: 10, text: "24 × 10 ＝ 240。" },
            { value: 310, place: 10, text: "24 × 3 ＝72。まず70を加えます。" },
            { value: 312, place: 1, text: "残り2を加えて312。" }
          ],
          quiz: { q: "24 × 13 で、最初の大きな部分積は？", options: ["24×1", "24×10", "24×3"], answer: "24×10" }
        },
        {
          id: "mul4",
          example: "40 × 6 ＝ ?",
          title: "0がある数の位取り",
          desc: "40×6で、4ではなく40を掛けていると意識する。",
          basic: "40×6は4×6＝24を使いますが、4は十の位です。答えは24ではなく240です。",
          trouble: "途中の0を『何もしないから無視』して位まで消してしまうこと。0は珠を置かなくても、位は残ります。",
          rule: "0の珠は置かなくても、0が示す位は消えない。",
          frames: [
            { value: 0, place: null, text: "40 × 6。4×6＝24を使います。" },
            { value: 200, place: 100, text: "40の4は十の位。答え24も1桁左へずれて240。" },
            { value: 240, place: 10, text: "十の位に4を置いて240。" }
          ],
          quiz: { q: "40 × 6 の答えは？", options: ["24", "240", "2400"], answer: "240" }
        }
      ]
    },
    div: {
      symbol: "÷",
      title: "割り算",
      desc: "商を見つけ、位をそろえて答えの珠を置くところから始めます。",
      lessons: [
        {
          id: "div1",
          example: "8 ÷ 4 ＝ ?",
          title: "1桁÷1桁",
          desc: "8÷4＝2。何個分あるかを考える。",
          basic: "割り算は『4が8の中に何個あるか』を考えます。4×2＝8なので商は2です。",
          trouble: "引き算を何回も繰り返すだけにしないこと。九九の逆として『4×いくつ＝8』を使います。",
          rule: "割り算は九九を逆向きに使う。",
          frames: [
            { value: 0, place: null, text: "8 ÷ 4。4×いくつで8になるか考えます。" },
            { value: 2, place: 1, text: "4×2＝8なので、商は2。答えの珠に2を置きます。" }
          ],
          quiz: { q: "8 ÷ 4 は？", options: ["2", "3", "4"], answer: "2" }
        },
        {
          id: "div2",
          example: "84 ÷ 4 ＝ ?",
          title: "2桁÷1桁",
          desc: "84÷4を十の位から見る。",
          basic: "84÷4は、大きい位から見ます。8十÷4＝2十、次に4÷4＝1。答えは21です。",
          trouble: "84を一気に考えようとしないこと。十の位→一の位に分けます。",
          rule: "割り算も大きい位から商を決める。",
          frames: [
            { value: 0, place: null, text: "84 ÷ 4。まず8十を4で割ります。" },
            { value: 20, place: 10, text: "8十 ÷4＝2十。十の位へ2。" },
            { value: 21, place: 1, text: "残る4 ÷4＝1。一の位へ1。答え21。" }
          ],
          quiz: { q: "84 ÷ 4 の十の位の商は？", options: ["1", "2", "4"], answer: "2" }
        },
        {
          id: "div3",
          example: "156 ÷ 3 ＝ ?",
          title: "3桁÷1桁",
          desc: "156÷3を左から順に処理する。",
          basic: "156÷3は、15十÷3＝5十、6÷3＝2と見ます。商は52です。",
          trouble: "最初の1だけを3で割れないから止まらないこと。必要なら次の桁と合わせて15として見ます。",
          rule: "先頭の数字が割れなければ、次の桁までまとめる。",
          frames: [
            { value: 0, place: null, text: "156 ÷ 3。先頭の1だけでは3で割れません。" },
            { value: 50, place: 10, text: "15を3で割ると5。十の位に5を置きます。" },
            { value: 52, place: 1, text: "残る6を3で割ると2。答え52。" }
          ],
          quiz: { q: "156 ÷ 3 で、最初に『15』を見る理由は？", options: ["1だけでは3で割れない", "6があるから", "いつも15を見る"], answer: "1だけでは3で割れない" }
        },
        {
          id: "div4",
          example: "144 ÷ 12 ＝ ?",
          title: "2桁で割る",
          desc: "144÷12で商を見当づける。",
          basic: "2桁で割るときは『12×いくつなら今見ている数を超えないか』を考えます。144÷12は12です。",
          trouble: "大きすぎる商を置いてから戻す回数を減らすため、まず上の桁を使って商を見当づけます。",
          rule: "商は『割る数×商が、今の数を超えない最大』を探す。",
          frames: [
            { value: 0, place: null, text: "144 ÷ 12。まず商の十の位を考えます。" },
            { value: 10, place: 10, text: "12×10＝120。144を超えないので十の位に1。" },
            { value: 12, place: 1, text: "残り24には12が2個。商は12。" }
          ],
          quiz: { q: "144 ÷ 12 の商は？", options: ["10", "12", "14"], answer: "12" }
        }
      ]
    }
  };

  const learningVoiceScripts = {
    add1: [
      "2 たす 2 です。まず、2を おきます。",
      "1つ、たします。",
      "もう1つ たします。4です。"
    ],
    add2: [
      "5 たす 3 です。まず、5を おきます。",
      "1つ、たします。",
      "もう1つ、たします。",
      "もう1つ たして、8です。"
    ],
    add3: [
      "2 たす 4 です。まず、2を おきます。",
      "4は そのまま たせません。先に、1を ひきます。",
      "つぎに、5を たします。6です。"
    ],
    add4: [
      "8 たす 7 です。まず、8を おきます。",
      "10を またぎます。先に、3を ひきます。",
      "つぎに、10を たします。15です。"
    ],
    add5: [
      "36 たす 27 です。まず、36を おきます。",
      "先に、20を たします。56です。",
      "つぎは 7。先に、3を ひきます。",
      "さいごに、10を たします。63です。"
    ],
    sub1: [
      "4 ひく 2 です。まず、4を おきます。",
      "1つ、ひきます。",
      "もう1つ ひきます。2です。"
    ],
    sub2: [
      "8 ひく 3 です。まず、8を おきます。",
      "1つ、ひきます。",
      "もう1つ、ひきます。",
      "もう1つ ひいて、5です。"
    ],
    sub3: [
      "7 ひく 4 です。まず、7を おきます。",
      "4を そのまま ひけません。先に、5を ひきます。",
      "つぎに、1を たします。3です。"
    ],
    sub4: [
      "12 ひく 7 です。まず、12を おきます。",
      "7を そのまま ひけません。先に、10を ひきます。",
      "つぎに、3を たします。5です。"
    ],
    sub5: [
      "43 ひく 28 です。まず、43を おきます。",
      "先に、20を ひきます。23です。",
      "つぎは 8。先に、10を ひきます。",
      "さいごに、2を たします。15です。"
    ],
    mul1: [
      "3 かける 4 です。答えは 12です。",
      "まず、10のくらいに 1を おきます。",
      "1のくらいに 2を おきます。12です。"
    ],
    mul2: [
      "23 かける 4 です。20と3に わけます。",
      "20 かける 4 は、80です。",
      "3 かける 4 は、12。まず、10を たします。",
      "つぎに、2を たします。92です。"
    ],
    mul3: [
      "24 かける 13 です。10と3に わけます。",
      "24 かける 10 は、240です。",
      "24 かける 3 は、72。まず、70を たします。",
      "つぎに、2を たします。312です。"
    ],
    mul4: [
      "40 かける 6 です。4 かける 6 は、24です。",
      "40なので、くらいを 1つ ずらします。まず、200です。",
      "つぎに、40を おきます。240です。"
    ],
    div1: [
      "8 わる 4 です。4が いくつあるか、かんがえます。",
      "4 かける 2 は 8。だから、答えは 2です。"
    ],
    div2: [
      "84 わる 4 です。大きい くらいから みます。",
      "8じゅう わる 4 は、2じゅう。20を おきます。",
      "4 わる 4 は 1。答えは 21です。"
    ],
    div3: [
      "156 わる 3 です。左から みます。",
      "1だけでは われません。15 わる 3 は 5。50を おきます。",
      "6 わる 3 は 2。答えは 52です。"
    ],
    div4: [
      "144 わる 12 です。答えを だいたい かんがえます。",
      "12 かける 10 は 120。まず、10を おきます。",
      "のこりは 24。12が 2こ。答えは 12です。"
    ]
  };

  let learningProgress = loadTutorialProgress();
  let learningCurrentCategory = null;
  let learningCurrentLessonIndex = 0;
  let learningRods = [];
  let learningAnimationToken = 0;
  let learningAnimationPaused = false;
  let learningCurrentFrame = 0;
  let learningVoiceEnabled = false;
  let learningNarrationToken = 0;

  // 補数名人：分類と解説を同じ珠操作列から生成する。
  const HOSU_STORAGE_KEY = "soroban_hosu_master_v1";
  const hosu = {
    op: "＋", level: 1, questions: [], index: 0, position: -1,
    correct: 0, hintQuestions: 0, mistakeQuestions: 0,
    questionWrong: false, questionHint: false, resolved: false,
    input: "", voice: false, recognition: null, token: 0,
    speaking: false, speechTimer: null, recognitionTimer: null, complete: false, recorded: false,
    pools: new Map(), stats: {}
  };
  try { hosu.stats = JSON.parse(localStorage.getItem(HOSU_STORAGE_KEY) || "{}"); }
  catch (error) { hosu.stats = {}; }
  if (!hosu.stats || typeof hosu.stats !== "object" || Array.isArray(hosu.stats)) hosu.stats = {};

  function buildHosuPlan(a, op, b) {
    if (!Number.isInteger(a) || !Number.isInteger(b) || a < 0 || b < 1 ||
        !["＋", "－"].includes(op) || (op === "－" && a < b)) {
      throw new Error("補数問題の数値が不正です。");
    }
    let value = a;
    const events = [];
    const digit = (place) => Math.floor(value / place) % 10;
    const move = (delta, place) => {
      const from = value;
      value += delta;
      if (value < 0) throw new Error("負の珠状態です。");
      const amount = Math.abs(delta / place);
      events.push({ kind: "move", from, value, place, delta,
        text: `${placeName(place)}で${amount}を${delta > 0 ? "足します" : "引きます"}。` });
    };
    const ask = (base, amount, sign, place) => {
      const answer = base - amount;
      events.push({ kind: "question", value, place, base, amount, sign, answer,
        text: `${placeName(place)}で${amount}を${sign > 0 ? "足す" : "引く"}ときに使う、${base}の補数はいくつ？`,
        explanation: `${amount}と${answer}で${base}です。` +
          (sign > 0 ? `${answer}を引いて${base}を足すと、${amount}を足せます。`
                    : `${base}を引いて${answer}を足すと、${amount}を引けます。`) });
    };
    const apply = (place, amount, sign, depth = 0) => {
      if (!amount) return;
      if (depth > 12) throw new Error("補数操作の再帰上限です。");
      const d = digit(place);
      if (sign > 0) {
        if (d + amount >= 10) {
          ask(10, amount, sign, place);
          apply(place, 10 - amount, -1, depth + 1);
          apply(place * 10, 1, 1, depth + 1);
        } else if (d < 5 && amount < 5 && d + amount >= 5) {
          ask(5, amount, sign, place);
          move(-(5 - amount) * place, place);
          move(5 * place, place);
        } else if (d < 5 && amount >= 5) {
          move(5 * place, place);
          if (amount > 5) move((amount - 5) * place, place);
        } else {
          move(amount * place, place);
        }
      } else {
        if (d < amount) {
          ask(10, amount, sign, place);
          apply(place * 10, 1, -1, depth + 1);
          apply(place, 10 - amount, 1, depth + 1);
        } else if (d >= 5 && amount < 5 && d % 5 < amount) {
          ask(5, amount, sign, place);
          move(-5 * place, place);
          move((5 - amount) * place, place);
        } else if (d >= 5 && amount >= 5) {
          move(-5 * place, place);
          if (amount > 5) move(-(amount - 5) * place, place);
        } else {
          move(-amount * place, place);
        }
      }
    };
    const groups = decomposeByPlace(b).map((part) => {
      const start = events.length;
      apply(part.place, part.digit, op === "＋" ? 1 : -1);
      const groupEvents = events.slice(start);
      const prompts = groupEvents.filter((event) => event.kind === "question");
      const chainCount = prompts.length;
      groupEvents.forEach((event) => {
        event.sourcePlace = part.place;
        event.sourceDigit = part.digit;
        event.chainCount = chainCount;
      });
      return { place: part.place, digit: part.digit, count: chainCount,
        mixed: prompts.some((event) => event.base === 5) && prompts.some((event) => event.base === 10) };
    });
    const answer = op === "＋" ? a + b : a - b;
    if (value !== answer) throw new Error("補数操作の結果が一致しません。");
    const prompts = events.filter((event) => event.kind === "question");
    const totalCount = prompts.length;
    const count = Math.max(0, ...groups.map((group) => group.count));
    return { a, op, b, answer, events, count, totalCount, groups,
      level: count === 0 ? 0 : count === 1 ? 1 : count === 2 ? 2 : 3,
      mixed: groups.some((group) => group.mixed),
      digits: String(Math.max(a, b, answer)).length };
  }

  function hosuPool(op, level) {
    const key = `${op}|${level}`;
    if (hosu.pools.has(key)) return hosu.pools.get(key);
    const unique = new Map();
    const consider = (a, b) => {
      if (op === "－" && a < b) return;
      const plan = buildHosuPlan(a, op, b);
      if (plan.level === level && plan.count <= 6) unique.set(`${a}|${b}`, plan);
    };
    // 1桁の基本と併用を先に網羅し、2〜3桁へ広げる。
    for (let a = 1; a <= 18; a += 1) {
      for (let b = 1; b <= 9; b += 1) consider(a, b);
    }
    if (level > 1) {
      for (let a = 10; a <= 99; a += 1) {
        for (let b = 1; b <= 9; b += 1) consider(a, b);
      }
      for (let attempt = 0; attempt < 1800; attempt += 1) {
        const a = randInt(10, level === 3 ? 999 : 99);
        const b = randInt(1, level === 3 ? 999 : 99);
        consider(a, b);
      }
    }
    const pool = [...unique.values()];
    if (pool.length < 12) throw new Error("補数問題を十分に生成できませんでした。");
    hosu.pools.set(key, pool);
    return pool;
  }

  function buildHosuQuestions(...args) {
    return appDiagnostics.measure("buildHosuQuestions", () => buildHosuQuestionsMeasured.apply(this,args));
  }
  function buildHosuQuestionsMeasured(op, level) {
    const pool = shuffleKuku(hosuPool(op, level));
    const selected = [];
    const add = (list, max) => {
      for (const plan of list) {
        if (selected.length >= max) break;
        if (!selected.includes(plan)) selected.push(plan);
      }
    };
    if (level === 1) {
      add(pool.filter((q) => q.events.some((e) => e.kind === "question" && e.base === 5)), 6);
      add(pool.filter((q) => q.events.some((e) => e.kind === "question" && e.base === 10)), 12);
    } else if (level === 2) {
      // 2回の中でも、まず5と10の併用を中心に練習する。
      add(pool.filter((q) => q.mixed && q.b < 10), 8);
    }
    add(pool, 12);
    return shuffleKuku(selected);
  }

  function stopHosuRecognition() {
    if (hosu.recognition) {
      const recognition = hosu.recognition;
      hosu.recognition = null;
      recognition.onend = null;
      try { recognition.abort(); } catch (error) {}
    }
  }

  function stopHosuSession() {
    hosu.token += 1;
    stopHosuRecognition();
    clearTimeout(hosu.speechTimer);
    clearTimeout(hosu.recognitionTimer);
    hosu.speaking = false;
    if ($("#hosuView")?.classList.contains("show") && "speechSynthesis" in window) {
      cancelAppSpeech();
    }
  }

  function speakHosu(text, onDone = null) {
    stopHosuRecognition();
    clearTimeout(hosu.recognitionTimer);
    const token = ++hosu.token;
    clearTimeout(hosu.speechTimer);
    hosu.speaking = true;
    let finished = false;
    hosu.interruptSpeech = () => {
      if (finished || token !== hosu.token) return;
      finished = true;
      clearTimeout(hosu.speechTimer);
      hosu.speaking = false;
      cancelAppSpeech();
    };
    const done = () => {
      if (finished || token !== hosu.token) return;
      finished = true;
      clearTimeout(hosu.speechTimer);
      hosu.speaking = false;
      if (onDone) onDone();
      // 読み上げ中も聞き取る。終了時にも必要なら聞き取りを再開する。
      if (token === hosu.token) queueHosuRecognition();
    };
    if (!("speechSynthesis" in window) || typeof SpeechSynthesisUtterance === "undefined") {
      done(); return;
    }
    cancelAppSpeech();
    hosu.speechTimer = setTimeout(done, Math.max(5000, text.length * 240));
    queueHosuRecognition(0);
    waitForJapaneseVoice(1000).then((voice) => {
      if (token !== hosu.token || finished || !$("#hosuView").classList.contains("show")) return;
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = "ja-JP";
      utterance.rate = 1.05;
      utterance.volume = appMasterVolume;
      if (voice) utterance.voice = voice;
      utterance.onend = done;
      utterance.onerror = done;
      try { window.speechSynthesis.resume(); speakWithAppVolume(utterance); }
      catch (error) { done(); }
    }).catch(done);
  }

  function renderHosuMenu() {
    const grid = $("#hosuModeGrid");
    grid.innerHTML = "";
    for (const op of ["＋", "－"]) {
      const section = document.createElement("section");
      section.className = "hosu-group";
      const heading = document.createElement("h3");
      heading.textContent = op === "＋" ? "足し算" : "引き算";
      section.appendChild(heading);
      const cards = document.createElement("div");
      cards.className = "hosu-cards";
      for (const level of [1, 2, 3]) {
        const card = document.createElement("article");
        card.className = "mode-card";
        const entry = hosu.stats[`${op}|${level}`] || {};
        const name = ["", "初級", "中級", "上級"][level];
        card.innerHTML = `<div class="mode-name">${name}</div><div class="mode-desc">補数の連鎖 ${level === 3 ? "3回以上" : `${level}回`}</div><div class="chips"><span class="chip">12問・時間なし</span></div><div class="hosu-record">挑戦 ${Number(entry.sessions) || 0}回｜最高 ${Number(entry.best) || 0}/12</div>`;
        const button = document.createElement("button");
        button.type = "button";
        button.className = "primary";
        button.textContent = "はじめる";
        button.dataset.hosuOp = op;
        button.dataset.hosuLevel = String(level);
        button.addEventListener("click", () => startHosuMode(op, level));
        card.appendChild(button);
        cards.appendChild(card);
      }
      section.appendChild(cards);
      grid.appendChild(section);
    }
  }

  function showHosuHome() {
    learningInterrupt();
    stopHosuSession();
    showHome();
    $("#homeView").classList.add("hidden");
    $("#hosuView").classList.add("show");
    $("#hosuMenu").classList.remove("hidden");
    $("#hosuGame").classList.add("hidden");
    $("#hosuResult").classList.add("hidden");
    renderHosuMenu();
  }

  function startHosuMode(...args) {
    return appDiagnostics.measure("startHosuMode", () => startHosuModeMeasured.apply(this,args));
  }
  function startHosuModeMeasured(op, level) {
    stopHosuSession();
    hosu.op = op;
    hosu.level = level;
    hosu.questions = buildHosuQuestions(op, level);
    hosuStampAttempt = beginSharedStamp("hosu", `${op === "＋" ? "足し算" : "引き算"}・${["","初級","中級","上級"][level]}`,12);
    learningMenu(hosuStampAttempt,`soroban:hosu:${op === "＋" ? "add" : "sub"}:${level}`,`soroban:complement:${op === "＋" ? "add" : "sub"}`,level);
    hosu.index = 0;
    hosu.correct = 0;
    hosu.hintQuestions = 0;
    hosu.mistakeQuestions = 0;
    hosu.recorded = false;
    hosu.voice = Boolean(getSpeechRecognitionClass());
    $("#hosuMenu").classList.add("hidden");
    $("#hosuResult").classList.add("hidden");
    $("#hosuGame").classList.remove("hidden");
    $("#hosuTitle").textContent = `${op === "＋" ? "足し算" : "引き算"}・${["", "初級", "中級", "上級"][level]}`;
    updateHosuVoiceUi();
    beginHosuQuestion();
  }

  function updateHosuVoiceUi() {
    $("#hosuVoiceBtn").textContent = hosu.voice ? "🎤 音声回答 ON" : "🎤 音声回答 OFF";
    $("#hosuVoiceBtn").classList.toggle("on", hosu.voice);
    const baseQuestion = !hosu.baseResolved;
    $("#hosuDigits").classList.toggle("hidden", hosu.voice || baseQuestion);
    $("#hosuBaseChoices").classList.toggle("hidden", hosu.voice || !baseQuestion);
  }

  function drawHosuBoard(value, activePlace = null) {
    const board = $("#hosuBoard");
    board.innerHTML = "";
    const q = hosu.questions[hosu.index];
    const max = Math.max(q.a, q.b, q.answer, ...q.events.map((event) => event.value));
    const count = String(max).length;
    for (let i = count - 1; i >= 0; i -= 1) {
      const place = 10 ** i;
      const rod = document.createElement("div");
      rod.className = "soroban-rod" + (place === activePlace ? " active" : "");
      const line = document.createElement("div"); line.className = "rod-line"; rod.appendChild(line);
      const upper = document.createElement("div"); upper.className = "soroban-bead upper-bead"; rod.appendChild(upper);
      const lowers = [];
      for (let n = 0; n < 4; n += 1) {
        const bead = document.createElement("div"); bead.className = "soroban-bead lower-bead";
        rod.appendChild(bead); lowers.push(bead);
      }
      const label = document.createElement("div"); label.className = "rod-place";
      label.textContent = shortPlaceName(place); rod.appendChild(label);
      setRodDigit({ upper, lowers }, Math.floor(value / place) % 10);
      board.appendChild(rod);
    }
    board.dataset.value = String(value);
  }

  function beginHosuQuestion() {
    stopHosuSession();
    learningQuestion(hosuStampAttempt,hosu.index,hosu.questions[hosu.index],"complement_steps");
    hosu.position = -1;
    hosu.questionWrong = false;
    hosu.questionHint = false;
    hosu.complete = false;
    hosu.resolved = false;
    renderHosuStep();
  }

  function hosuActionPrompt(event) {
    const amount = Math.abs(event.delta / event.place);
    return event.delta > 0
      ? `${placeName(event.place)}に${amount}を足してね。`
      : `${placeName(event.place)}から${amount}を引いてね。`;
  }

  function hosuComplementAction(event) {
    const unit = event.base * event.place;
    const complement = event.answer * event.place;
    return event.sign > 0
      ? `${event.amount}の${event.base}の補数は${event.answer}なので、${complement}を引いて${unit}を足しましょう。`
      : `${event.amount}の${event.base}の補数は${event.answer}なので、${unit}を引いて${complement}を足しましょう。`;
  }

  function hosuComplementReason(event) {
    const digit = Math.floor(event.value / event.place) % 10;
    if (event.base === 10) {
      return event.sign > 0
        ? `${digit}に${event.amount}を足すと繰り上がるよ。5の補数では繰り上がれないので、10の補数を使うよ。`
        : `${digit}から${event.amount}は引けないよ。5の補数では足りないので、となりの位から借りる10の補数を使うよ。`;
    }
    return event.sign > 0
      ? `繰り上がらないので、10の補数は使わないよ。下の珠だけでは足せないので、5の珠に置き換える5の補数を使うよ。`
      : `となりの位から借りなくていいので、10の補数は使わないよ。下の珠だけでは引けないので、5の珠を取って戻す5の補数を使うよ。`;
  }

  function renderHosuStep(keepBase = false) {
    learningTick();if(learningClock){learningClock.substep=hosu.position<0?null:String(hosu.position);learningClock.cmPhase=hosu.questions[hosu.index]?.events[hosu.position]?.kind==="question"&&!hosu.baseResolved?"thinking":"exploration";}
    stopHosuSession();
    const q = hosu.questions[hosu.index];
    const event = q.events[hosu.position];
    hosu.input = "";
    if (!keepBase) hosu.baseResolved = false;
    hosu.resolved = event?.kind === "question" && hosu.baseResolved;
    $("#hosuAnswer").textContent = "\u00a0";
    $("#hosuVoiceStatus").textContent = "";
    $("#hosuFeedback").textContent = "";
    $("#hosuFeedback").className = "feedback";
    $("#hosuExplanation").classList.add("hidden");
    $("#hosuProgress").textContent = `${hosu.index + 1} / 12｜自力正解 ${hosu.correct}`;
    $("#hosuEquation").textContent = `${q.a} ${q.op} ${q.b} ＝ ${hosu.complete ? q.answer : "?"}`;
    $("#hosuCount").textContent = `補数の連鎖 最大${q.count}回｜${q.digits}桁`;
    const introduction = "5の補数、10の補数かを最初に考えてから、補数になる数を引きましょう。";
    const showIntro = hosu.index === 0 && hosu.position < 0 && q.op === "＋" && !hosu.complete;
    $("#hosuIntro").textContent = showIntro ? introduction : "";
    $("#hosuIntro").classList.toggle("hidden", !showIntro);
    const prompt = !hosu.complete && event?.kind === "question";
    const answering = prompt && !hosu.resolved;
    $("#hosuAnswerArea").classList.toggle("hidden", !answering);
    updateHosuVoiceUi();
    $("#hosuHintBtn").classList.toggle("hidden", !prompt);
    $("#hosuNextBtn").disabled = answering;
    $("#hosuNextBtn").textContent = hosu.complete
      ? (hosu.index === 11 ? "結果を見る" : "次の問題へ")
      : answering ? "補数を答えてね" : "できた";
    const text = hosu.complete
      ? (hosu.voice ? "できたね。「つぎ」と言ってね。" : "できたね。")
      : hosu.position < 0
        ? `${q.a}を置いてね。できたら「できた」を${hosu.voice ? "言ってね" : "押してね"}。`
        : event.kind === "move" ? hosuActionPrompt(event)
        : !hosu.baseResolved
          ? `${event.amount}を${event.sign > 0 ? "足す" : "引く"}とき、5の補数？10の補数？どっちになる？`
          : hosuComplementAction(event);
    if(hosu.baseResolved&&event?.kind==="question"&&!hosu.complete){const cq=hosuStampAttempt?.questions[String(hosu.index)];const key="answer:"+hosu.position;if(cq&&!cq[key]){cq[key]=true;cmSupport(hosuStampAttempt,cq,"answer",String(hosu.position),null,true);}}
    $("#hosuPrompt").textContent = text;
    // 先に完成形を見せず、手元で操作して確認した時だけ画面の珠を更新する。
    const shown = hosu.complete ? q.answer
      : event?.kind === "move" ? event.from : event ? event.value : q.a;
    drawHosuBoard(shown, hosu.complete ? null : event?.place);
    if (showIntro) {
      speakHosu(introduction, () => {
        // 1文ずつ読み、説明と操作の声かけをまとめて長くしない。
        if (hosu.index === 0 && hosu.position < 0 &&
            $("#hosuView").classList.contains("show") && !$("#hosuGame").classList.contains("hidden")) {
          speakHosu(text);
        }
      });
    } else speakHosu(text);
  }

  function submitHosuAnswer(value) {
    const q = hosu.questions[hosu.index];
    const event = q?.events[hosu.position];
    if (!$("#hosuView").classList.contains("show") || hosu.complete ||
        event?.kind !== "question" || hosu.resolved || value === "") return;
    const user = Number(value);
    if (!hosu.baseResolved) {
      if (user !== 5 && user !== 10) return;
      learningResponse(hosuStampAttempt,hosu.index,user===event.base,`${hosu.position}:base`,user,null,event.base);
      stopHosuRecognition();
      if (user === event.base) {
        hosu.baseResolved = true;
        renderHosuStep(true);
      } else {
        hosu.questionWrong = true;
        $("#hosuFeedback").textContent = "もういちど考えよう。";
        $("#hosuFeedback").className = "feedback bad";
        speakHosu("もういちど。5？ 10？");
      }
      return;
    }
    if (!Number.isInteger(user) || user < 1 || user > 9) return;
    learningResponse(hosuStampAttempt,hosu.index,user===event.answer,`${hosu.position}:complement`,user,null,event.answer);
    hosu.input = String(user);
    $("#hosuAnswer").textContent = hosu.input;
    stopHosuRecognition();
    const ok = user === event.answer;
    if (ok) {
      hosu.resolved = true;
      $("#hosuFeedback").textContent = "せいかい！";
      $("#hosuFeedback").className = "feedback good";
      $("#hosuNextBtn").disabled = true;
      const answeredIndex = hosu.index;
      const answeredPosition = hosu.position;
      // 補数が分かったら、ボタン待ちを挟まず実物での操作を促す。
      speakHosu("せいかい！", () => {
        if (hosu.index !== answeredIndex || hosu.position !== answeredPosition ||
            !hosu.resolved || !$("#hosuView").classList.contains("show") ||
            $("#hosuGame").classList.contains("hidden")) return;
        $("#hosuNextBtn").disabled = false;
        nextHosuStep();
      });
    } else {
      hosu.questionWrong = true;
      $("#hosuFeedback").textContent = "もういちど考えよう。";
      $("#hosuFeedback").className = "feedback bad";
      speakHosu("ざんねん。もういちど。");
    }
  }

  function nextHosuStep() {
    if ($("#hosuNextBtn").disabled) return;
    const q = hosu.questions[hosu.index];
    const event = q?.events[hosu.position];
    if (!q || (event?.kind === "question" && !hosu.resolved && !hosu.complete)) return;
    if (hosu.complete) {
      hosu.index += 1;
      if (hosu.index === 12) finishHosuMode();
      else beginHosuQuestion();
      return;
    }
    cmEmit(hosuStampAttempt,"learning_activity",{activity_type:"operation_acknowledged",substep_id:String(hosu.position),result:null,observation_basis:"done_command_only; physical_beads_not_observed"},hosuStampAttempt?.questions[String(hosu.index)]);
    hosu.position += 1;
    // 「できた」で、案内した補数操作に含まれる珠移動をまとめて確認する。
    if (event?.kind === "question" && hosu.resolved) {
      while (q.events[hosu.position]?.kind === "move") hosu.position += 1;
    }
    if (hosu.position >= q.events.length) {
      hosu.complete = true;
      if (hosu.questionHint) hosu.hintQuestions += 1;
      else if (hosu.questionWrong) hosu.mistakeQuestions += 1;
      else hosu.correct += 1;
      recordSharedStampAnswer(hosuStampAttempt,hosu.index,!hosu.questionWrong && !hosu.questionHint);
    }
    renderHosuStep();
  }

  function hosuVoicePhase() {
    if (!hosu.voice || !$("#hosuView").classList.contains("show") ||
        $("#hosuGame").classList.contains("hidden")) return null;
    const event = hosu.questions[hosu.index]?.events[hosu.position];
    if (hosu.complete) return "next";
    if (event?.kind === "question") return hosu.resolved ? "done" : "base";
    return hosu.position < 0 || event?.kind === "move" ? "done" : null;
  }

  function queueHosuRecognition(delay = 200) {
    if (!hosuVoicePhase()) return;
    clearTimeout(hosu.recognitionTimer);
    const token = hosu.token;
    hosu.recognitionTimer = setTimeout(() => {
      if (token === hosu.token) startHosuRecognition();
    }, delay);
  }

  function hosuCommandMatches(result, phase) {
    const pattern = phase === "next"
      ? /^(?:つぎ|次|つぎへ|次へ|次の問題|次の問題へ|結果|結果を見る)$/
      : /^(?:できた|出来た|できました|出来ました|おわった|終わった|おわりました|終わりました)$/;
    for (let i = 0; i < (result?.length || 0); i += 1) {
      const text = String(result[i]?.transcript || "").replace(/[\s、。,.！!？?]/g, "");
      if (pattern.test(text)) return true;
    }
    return false;
  }

  function fallbackHosuVoice(message) {
    stopHosuRecognition();
    hosu.voice = false;
    updateHosuVoiceUi();
    renderHosuStep(true);
    $("#hosuVoiceStatus").textContent = message;
  }

  function selectHosuNumericSpeech(result, phase) {
    // 質問に使える範囲の候補だけを比較する。正解そのものでは絞らない。
    const candidates = [];
    for (let i = 0; i < (result?.length || 0); i += 1) {
      const alternative = result[i];
      const transcript = String(alternative?.transcript || "")
        .replace(/[ァ-ヶ]/g, (c) => String.fromCharCode(c.charCodeAt(0) - 0x60))
        .replace(/[\s、。,.！!？?]/g, "")
        .replace(/(?:の)?(?:補数|ほすう)/g, "");
      const candidate = { transcript, confidence: alternative?.confidence };
      const selected = phase === "base"
        ? selectBestNumericSpeech([candidate]) : selectBestHintSingleDigitSpeech([candidate]);
      if (selected && (phase !== "base" || selected.value === 5 || selected.value === 10)) {
        candidates.push(candidate);
      }
    }
    return phase === "base"
      ? selectBestNumericSpeech(candidates) : selectBestHintSingleDigitSpeech(candidates);
  }

  function startHosuRecognition() {
    const phase = hosuVoicePhase();
    if (!phase || hosu.recognition) return;
    const Recognition = getSpeechRecognitionClass();
    if (!Recognition) {
      fallbackHosuVoice("このブラウザでは音声回答を使えません。数字とボタンで進めてね。");
      return;
    }
    const token = hosu.token;
    const questionIndex = hosu.index;
    const position = hosu.position;
    const recognition = new Recognition();
    appDiagnostics.observeRecognition(recognition);
    hosu.recognition = recognition;
    // チャレンジ本体と同じ認識設定・残響ガード・判定待ち時間を使う。
    recognition.lang = "ja-JP";
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.maxAlternatives = 5;
    let startedAt = null;
    let accepted = false;
    const sameStep = () => token === hosu.token && questionIndex === hosu.index &&
      position === hosu.position && hosuVoicePhase() === phase;
    const current = () => sameStep() && hosu.recognition === recognition;
    const instruction = phase === "base" ? "🎤 5の補数か10の補数で答えてね"
      : phase === "done" ? "🎤 動かせたら「できた」と言ってね" : "🎤 進むときは「つぎ」と言ってね";
    const retry = (delay) => {
      if (accepted || !sameStep()) return;
      if (hosu.recognition === recognition) stopHosuRecognition();
      queueHosuRecognition(delay);
    };
    recognition.onstart = () => {
      if (!current()) return;
      startedAt = Date.now();
      $("#hosuVoiceStatus").textContent = instruction;
    };
    recognition.onspeechstart = () => {
      if (!current() || accepted) return;
      // 発話検知はアプリの読み上げや環境音でも起こるため、ここでは止めない。
      // 有効な回答を認識したonresultでのみ案内音声を中断する。
      $("#hosuVoiceStatus").textContent = "🎤 聞いています…";
    };
    recognition.onspeechend = () => {
      if (current() && !accepted) $("#hosuVoiceStatus").textContent = "🎤 確認中…";
    };
    recognition.onresult = (event) => {
      cmLastInput="speech";
      if (!current() || accepted) return;
      if (startedAt === null || Date.now() - startedAt < MIC_RESULT_GUARD_MS) return;
      const result = event.results?.[0];
      const selected = phase === "base" ? selectHosuNumericSpeech(result, phase) : null;
      const command = phase !== "base" && hosuCommandMatches(result, phase);
      if (!selected && !command) {
        $("#hosuVoiceStatus").textContent = instruction;
        return;
      }
      accepted = true;
      hosu.interruptSpeech?.();
      // チャレンジと同じくstop→160ms後に確定。onendの到着には依存しない。
      try { recognition.stop(); } catch (error) {}
      clearTimeout(hosu.recognitionTimer);
      hosu.recognitionTimer = setTimeout(() => {
        if (!sameStep()) return;
        if (hosu.recognition === recognition) {
          hosu.recognition = null;
          recognition.onend = null;
          recognition.onerror = null;
        }
        if (selected) submitHosuAnswer(selected.value);
        else nextHosuStep();
      }, 160);
    };
    recognition.onerror = (event) => {
      if(learningActive)cmEmit(learningActive,"learning_activity",{activity_type:"recognition_failed",substep_id:null,result:null,observation_basis:"speech_api_error:"+String(event?.error||"unknown")},learningActive.questions[String(learningClock?.index)]);
      if (!current() || accepted) return;
      if (["not-allowed", "service-not-allowed", "audio-capture"].includes(event.error)) {
        fallbackHosuVoice("マイクを使えません。数字とボタンで進めてね。");
      } else {
        retry(["no-speech", "aborted"].includes(event.error) ? 380 : 500);
      }
    };
    recognition.onend = () => {
      if (hosu.recognition !== recognition) return;
      hosu.recognition = null;
      if (!accepted && sameStep()) queueHosuRecognition(320);
    };
    try { recognition.start(); }
    catch (error) { retry(500); }
  }

  // Chokomana common learning contract v1. All durations are measured seconds.
  const STAMP_CATEGORIES = {
    calculation:{category_key:'calculation',category_label:'そろばん・計算',stamp_char:'算',reading:'さん'},
    hosu:{category_key:'hosu',category_label:'補数名人',stamp_char:'補',reading:'ほ'},
    kuku:{category_key:'kuku',category_label:'九九名人',stamp_char:'九',reading:'きゅう'},
    anzan:{category_key:'anzan',category_label:'暗算名人',stamp_char:'暗',reading:'あん'}
  };
  const LEARNING_STORE='chokomana_soroban_learning_v1', LEARNING_LEASE='chokomana_soroban_learning_lease_v1';
  const safeRead=(key,fallback)=>{try{return JSON.parse(localStorage.getItem(key))||fallback}catch(e){return fallback}};
  const safeWrite=(key,value)=>{try{localStorage.setItem(key,JSON.stringify(value));return true}catch(e){return false}};
  function stampUuid(){try{return crypto.randomUUID()}catch(e){try{const b=new Uint8Array(16);crypto.getRandomValues(b);b[6]=(b[6]&15)|64;b[8]=(b[8]&63)|128;const h=Array.from(b,x=>x.toString(16).padStart(2,'0')).join('');return `${h.slice(0,8)}-${h.slice(8,12)}-${h.slice(12,16)}-${h.slice(16,20)}-${h.slice(20)}`}catch(e){return null}}}
  const learningTab=stampUuid();
  let learningState=safeRead(LEARNING_STORE,{attempts:{},pending:{}});
  if(!learningState.attempts||!learningState.pending)learningState={attempts:{},pending:{}};
  let stampProfile='', stampConfigSeen=false, learningActive=null, learningClock=null, learningInFlight=null, learningRetry=null,learningRetryCount=0,learningNextSend=0;
  let tutorialStampAttempt=null;
  let mainStampAttempt=null,hosuStampAttempt=null,kukuStampAttempt=null,anzanStampAttempt=null;
  let learningDevice='';
  try{learningDevice=localStorage.getItem('chokomana_device_identity_v1_soroban')||'';if(!/^[a-f0-9]{64}$/.test(learningDevice)){const b=new Uint8Array(32);crypto.getRandomValues(b);learningDevice=Array.from(b,x=>x.toString(16).padStart(2,'0')).join('');localStorage.setItem('chokomana_device_identity_v1_soroban',learningDevice)}}catch(e){}
  const learningTotals=()=>({answer_seconds:0,explanation_seconds:0,review_seconds:0,hidden_seconds:0,break_seconds:0,network_wait_seconds:0,unmeasured_seconds:0});
  function learningOwn(a){const lease=safeRead(LEARNING_LEASE,{});return lease.attempt_id===a.attempt_id&&lease.owner===learningTab}
  function learningClaim(a){const lease=safeRead(LEARNING_LEASE,{});if(lease.attempt_id===a.attempt_id&&lease.owner!==learningTab&&lease.until>Date.now())return false;return safeWrite(LEARNING_LEASE,{attempt_id:a.attempt_id,owner:learningTab,until:Date.now()+15000})}
  function learningSave(){
    // Merge other tabs' attempts. An attempt is only written by its current lease owner.
    const disk=safeRead(LEARNING_STORE,{attempts:{},pending:{}});
    for(const [id,a] of Object.entries(disk.attempts||{}))if(!learningState.attempts[id]||a.revision>learningState.attempts[id].revision)learningState.attempts[id]=a;
    for(const [id,a] of Object.entries(disk.pending||{}))if(!learningState.pending[id]||a.revision>learningState.pending[id].revision)learningState.pending[id]=a;
    if(!safeWrite(LEARNING_STORE,learningState)&&learningActive)learningActive.storage_persistent=false;
  }
  function learningTick(){
    const a=learningActive,c=learningClock;if(!a||!c)return;
    if(c.index<0){c.perf=performance.now();c.wall=Date.now();return;}
    const now=performance.now();let elapsed=Math.max(0,(now-c.perf)/1000);c.perf=now;if(c.wall!==undefined&&Math.abs(Date.now()-c.wall-elapsed*1000)>2000)a.timing_quality='clock_changed';c.wall=Date.now();
    if(!learningOwn(a)){a.timing_quality='contended';return}
    const bucket=c.hidden?'hidden_seconds':c.paused?'break_seconds':c.phase+'_seconds';
    a.time[bucket]+=elapsed;
    if(['answer_seconds','explanation_seconds','review_seconds'].includes(bucket)){
      const end=Date.now(),start=end-elapsed*1000;let cursor=start;
      while(cursor<end){const date=new Date(cursor+9*3600000).toISOString().slice(0,10);const boundary=Date.parse(date+'T00:00:00Z')+15*3600000;const stop=Math.min(end,boundary);a.daily_active_seconds[date]=(a.daily_active_seconds[date]||0)+(stop-cursor)/1000;cursor=stop;}
    }
    const q=a.questions[String(c.index)];if(q)q.time[bucket]+=elapsed;
    cmInterval(a,c,elapsed,new Date(Date.now()-elapsed*1000).toISOString(),new Date().toISOString(),bucket);
    a.updated_at=new Date().toISOString();a.revision+=1;
    safeWrite(LEARNING_LEASE,{attempt_id:a.attempt_id,owner:learningTab,until:Date.now()+15000});
  }
  function learningPhase(phase){learningTick();if(learningClock){learningClock.phase=phase;learningClock.cmPhase=null;}}
  function learningQuestion(a,index,q,format='numeric'){
    if(!a||a.status!=='active'||a!==learningActive||!learningOwn(a))return;
    cmStart(a);learningTick();
    const key=String(index),canonical=JSON.stringify(q.terms?{terms:q.terms,operators:q.operators||null}: {a:q.a,op:q.op||'×',b:q.b});
    // Canonical expression itself is an exact stable ID, avoiding hash collisions.
    const id='soroban:problem:v1:'+canonical;
    const isNew=!a.questions[key];if(isNew)a.questions[key]={question_order:index+1,problem_id:id,variant_group:a.menu_id,skill_ids:learningSkills(a,q),difficulty:a.difficulty,format,first_correct:null,retry_count:0,hint_used:false,explanation_used:false,submitted_steps:{},time:learningTotals(),same_problem_seen:Object.values(learningState.attempts).some(t=>t.profile_id===a.profile_id&&Object.values(t.questions||{}).some(p=>p.problem_id===id)),displayed_at:new Date().toISOString()};
    if(isNew)cmPresent(a,a.questions[key],q);
    learningClock.index=index;learningClock.phase='answer';learningClock.perf=performance.now();learningSave();
  }
  function learningSkills(a,q){
    if(a.cmMenu?.mode_kind==='tutorial')return [a.skill_id];
    if(a.category_key==='hosu')return [...new Set([a.skill_id,...(q.events||[]).filter(e=>e.kind==='question').map(e=>'soroban:complement:'+e.base)])];
    if(a.category_key==='kuku')return ['soroban:multiplication','soroban:kuku:'+q.a];
    if(a.category_key==='anzan')return [a.skill_id,...new Set((q.terms||[]).map(t=>t.op==='－'?'soroban:mental_subtraction':'soroban:mental_addition'))];
    const ops=q.operators||[q.op];return [...new Set(ops.map(o=>({'＋':'soroban:add','－':'soroban:sub','×':'soroban:mul','÷':'soroban:div'})[o]).filter(Boolean))];
  }
  function learningHint(a,index){const q=a?.questions[String(index)];if(!q)return;learningPhase('explanation');q.hint_used=true;q.explanation_used=true;cmSupport(a,q,'hint',null,null,true);cmSupport(a,q,'explanation',null,null,true);learningSave()}
  function learningResponse(a,index,ok,step='answer',value=null,input=null,expected=null){
    const q=a?.questions[String(index)];if(!q||a.status!=='active'||!learningOwn(a))return;
    learningTick();cmResponse(a,q,ok,value,step,input,'answered',expected);const n=q.submitted_steps[step]||0;q.submitted_steps[step]=n+1;if(n)q.retry_count+=1;
    if(n===0){if(q.first_correct===null)q.first_correct=Boolean(ok);else if(!ok)q.first_correct=false;}
    // For multi-step complement tasks, first_correct means every step's FIRST answer was correct.
    if(n&&ok){} // A retry never repairs a previous false value.
    learningSave();
  }
  function learningSnapshot(a,status,emitEnd=true){
    learningTick();a.revision+=1;a.status=status;a.finished_at=new Date().toISOString();
    a.active_seconds=a.time.answer_seconds+a.time.explanation_seconds+a.time.review_seconds;
    a.elapsed_seconds=Math.max(0,(Date.parse(a.finished_at)-Date.parse(a.started_at))/1000);
    a.correct_count=Object.values(a.answers).filter(Boolean).length;if(emitEnd)cmEnd(a,status==='completed'?'completed':a.end_reason||'abandoned');
    if(a.profile_id)learningState.pending[a.attempt_id]=JSON.parse(JSON.stringify(a));
    learningSave();
  }
  function learningInterrupt(){if(learningActive?.status==='active'){const a=learningActive;learningSnapshot(a,'interrupted');learningClock=null;learningActive=null;sendSharedStamp()}}
  function beginSharedStamp(kind,difficulty,total,resume=null){
    learningInterrupt();
    const old=resume?.attempt_id&&learningState.attempts[resume.attempt_id];
    let a=old&&(!stampConfigSeen||old.profile_id===(stampProfile||null))&&old.status!=='completed'?old:null;
    const legacy=resume?.schema_version===2&&resume.total_count===total&&resume.profile_id===stampProfile&&/^[0-9a-f-]{36}$/i.test(resume.attempt_id);
    if(!a){const id=legacy?resume.attempt_id:stampUuid();if(!id)return null;a={schema_version:3,attempt_id:id,profile_id:stampProfile||null,category_key:kind,difficulty,total_count:total,answers:{},questions:{},started_at:new Date().toISOString(),daily_active_seconds:{},time:learningTotals(),revision:0,status:'active',timing_quality:'measured',storage_persistent:true,content_version:'soroban-material-167',menu_id:'',skill_id:''};}
    else{a.time.unmeasured_seconds+=Math.max(0,(Date.now()-Date.parse(a.updated_at||a.finished_at||a.started_at))/1000);a.timing_quality='partial_resume';}
    if(legacy){a.answers={...resume.answers};a.started_at=resume.started_at;a.timing_quality='legacy_partial';a.legacy_source={source_format:'soroban_stamp_attempt_v2',legacy_record_id:resume.attempt_id,imported_at:new Date().toISOString(),missing_fields:['events_before_upgrade','precise_active_time'],original_payload:resume};}
    a.status='active';a.finished_at=null;learningState.attempts[a.attempt_id]=a;
    if(!learningClaim(a)){a.timing_quality='contended';return null}
    learningActive=a;learningClock={perf:performance.now(),index:-1,phase:'unmeasured',paused:false,hidden:Boolean(document.hidden),wall:Date.now()};learningSave();return a;
  }
  function learningMenu(a,id,skill,order){if(!a)return;a.menu_id=id;a.skill_id=skill;a.difficulty_order=order;}
  function gradeSharedScore(correct,total){return correct===total?'gold':correct>=Math.ceil(total*5/6)?'silver':correct>=Math.ceil(total*2/3)?'bronze':'white'}
  function recordSharedStampAnswer(a,index,correct){if(!a||a.status!=='active'||!learningOwn(a))return;learningTick();if(!Object.prototype.hasOwnProperty.call(a.answers,String(index)))a.answers[String(index)]=Boolean(correct);const q=a.questions[String(index)];if(q){if(q.first_correct===null)q.first_correct=Boolean(correct);q.completed=true;q.answered_at=new Date().toISOString();}learningPhase('review');learningSave()}
  let dailyMedalAttempt = null;
  let dailyMedalReturnFocus = null;
  function closeDailyMedal() {
    $("#dailyMedalPopup").classList.add("hidden");
    dailyMedalAttempt = null;
    if (dailyMedalReturnFocus?.isConnected) dailyMedalReturnFocus.focus?.({preventScroll:true});
  }
  function dailyMedalNotice(a, status) {
    if (!a || a.status !== 'completed' || Object.keys(a.answers).length !== a.total_count) return;
    if (status === 'saved' && (a.profile_id !== stampProfile || a.daily_medal_notified)) return;
    const category = STAMP_CATEGORIES[a.category_key];
    if (!category) return;
    if (status === 'saved') { a.daily_medal_notified = true; learningSave(); }
    const popup = $("#dailyMedalPopup");
    const opening = popup.classList.contains('hidden');
    const grade = ['gold','silver','bronze','white'].includes(a.grade) ? a.grade : 'white';
    const names = {gold:'金',silver:'銀',bronze:'銅',white:'白'};
    const icon = $("#dailyMedalIcon");
    icon.className = 'cm-stamp ' + grade;
    icon.setAttribute('aria-label', names[grade] + 'のデイリーメダル ' + category.stamp_char);
    $("#dailyMedalGrade").textContent = names[grade];
    $("#dailyMedalChar").textContent = category.stamp_char;
    $("#dailyMedalReading").textContent = category.reading;
    $("#dailyMedalCategory").textContent = category.category_label + '　' + a.correct_count + ' / ' + a.total_count + '問';
    $("#dailyMedalTitle").textContent = status === 'saved' ? 'デイリーメダルを獲得しました' : '学習をやり切りました！';
    $("#dailyMedalStatus").textContent = status === 'saved' ? 'ちょこまなの「今日の成果」に保存しました。'
      : status === 'unlinked' ? 'ちょこまなに未連携のため、デイリーメダルは保存されていません。'
      : status === 'failed' ? 'まだ保存できていません。学習記録を端末に保持し、自動で再送します。'
      : 'デイリーメダルをちょこまなに保存しています…';
    dailyMedalAttempt = a.attempt_id;
    if (opening) dailyMedalReturnFocus = document.activeElement;
    popup.classList.remove('hidden');
    if (opening) $("#dailyMedalClose").focus?.({preventScroll:true});
  }
  $("#dailyMedalClose").addEventListener('click', closeDailyMedal);
  $("#dailyMedalPopup").addEventListener('keydown', event => {
    if (event.key === 'Escape') { event.preventDefault(); closeDailyMedal(); }
    if (event.key === 'Tab') { event.preventDefault(); $("#dailyMedalClose").focus?.({preventScroll:true}); }
  });

  function completeSharedStamp(a,grade){
    if(!a||a.status!=='active')return;
    if(Object.keys(a.answers).length!==a.total_count){learningInterrupt();return;}
    a.grade=['hosu','anzan'].includes(a.category_key)?gradeSharedScore(Object.values(a.answers).filter(Boolean).length,a.total_count):grade;
    learningSnapshot(a,'completed');learningActive=null;learningClock=null;dailyMedalNotice(a,a.profile_id?'saving':'unlinked');sendSharedStamp();
  }
  function sendSharedStamp(){
    if(!stampConfigSeen||!stampProfile||learningInFlight||!learningDevice||Date.now()<learningNextSend)return;
    const a=Object.values(learningState.pending).find(a=>a.profile_id===stampProfile);
    const events=[];let size=0;for(const e of Object.values(cmEvents.pending)){if(e.profile_id!==stampProfile)continue;const bytes=JSON.stringify(e).length;if(events.length>=50||size+bytes>200000)break;events.push(e);size+=bytes;}
    if(!a&&!events.length)return;const delivery=stampUuid();if(!delivery)return;
    learningInFlight={attempt_id:a?.attempt_id,delivery_id:delivery,revision:a?.revision,event_ids:events.map(e=>e.event_id)};
    window.parent.postMessage({isStreamlitMessage:true,type:'streamlit:setComponentValue',value:{events,learning:a||null,device_token:learningDevice,delivery_id:delivery}},'*');
    clearTimeout(learningRetry);learningRetry=setTimeout(()=>{learningInFlight=null;learningRetryCount++;sendSharedStamp()},Math.min(300000,30000*(2**Math.min(learningRetryCount,4))));
  }
  function learningIdentity(){if(learningDevice)window.parent.postMessage({isStreamlitMessage:true,type:'streamlit:setComponentValue',value:{identity:true,device_token:learningDevice,delivery_id:stampUuid()}},'*')}
  window.addEventListener('message',event=>{
    if(event.source!==window.parent||event.data?.type!=='streamlit:render')return;
    const args=event.data.args||{};const statusEl=$('#chokomanaLinkStatus');if(statusEl&&!cmStorageFailed)statusEl.textContent=args.link_status==='linked'?'ちょこまな連携：接続済み（未送信記録は同じ学習者のときに再送します）':'ちょこまな連携：未接続。集約アプリから開いてください。学習は続けられます。';const next=String(args.stamp_profile_id||'');
    if(stampConfigSeen&&next!==stampProfile){learningInterrupt();learningInFlight=null;clearTimeout(learningRetry);}
    stampProfile=next;stampConfigSeen=true;
    // Only a fresh, still-active challenge may receive the first verified identity.
    if(learningActive&&!learningActive.profile_id&&next&&Object.keys(learningActive.questions).length===0)learningActive.profile_id=next;
    const ack=args.stamp_result;
    if(ack&&learningInFlight&&ack.delivery_id===learningInFlight.delivery_id){
      const sent=learningInFlight;clearTimeout(learningRetry);learningInFlight=null;
      for(const id of ack.acked||[])if(sent.event_ids.includes(id)){cmEvents.acked[id]=true;delete cmEvents.pending[id];}cmPersist();
      if(ack.ok && ack.stamp_ok)dailyMedalNotice(learningState.attempts[sent.attempt_id],'saved');
      if(!ack.ok && dailyMedalAttempt===sent.attempt_id)dailyMedalNotice(learningState.attempts[sent.attempt_id],'failed');
      if(ack.stamp_ok){const pending=learningState.pending[sent.attempt_id];if(pending&&pending.revision<=sent.revision){delete learningState.pending[sent.attempt_id];const disk=safeRead(LEARNING_STORE,{attempts:{},pending:{}});delete disk.pending[sent.attempt_id];safeWrite(LEARNING_STORE,disk);}learningSave();}
      if(!ack.ok){if(statusEl&&!cmStorageFailed)statusEl.textContent='ちょこまな連携：記録は未送信です。接続・DB設定を確認後に自動再送します。';learningRetryCount++;const wait=Math.min(300000,2000*(2**Math.min(learningRetryCount,8)));learningNextSend=Date.now()+wait;learningRetry=setTimeout(()=>{learningNextSend=0;sendSharedStamp()},wait);return;}learningRetryCount=0;learningNextSend=0;
    }
    sendSharedStamp();
  });
  setInterval(()=>{if(learningActive){learningTick();learningSave()}},5000);
  setInterval(sendSharedStamp,30000);
  window.addEventListener('pagehide',()=>{if(learningActive){cmEmit(learningActive,'session_paused',{reason:'pagehide',suspended_occurrence_id:learningActive.questions[String(learningClock?.index)]?.occurrence_id||null,last_response_id:null});learningSnapshot(learningActive,'interrupted',false);learningClock=null;safeWrite(LEARNING_LEASE,{});}});
  document.addEventListener('visibilitychange',()=>{
    // Flush using the PREVIOUS visibility state before changing the clock's bucket.
    if(learningActive&&learningClock){const hidden=document.hidden;learningTick();learningClock.hidden=hidden;cmEmit(learningActive,hidden?'session_paused':'session_resumed',{reason:'tab_visibility',suspended_occurrence_id:learningActive.questions[String(learningClock.index)]?.occurrence_id||null,last_response_id:null});learningSave();if(hidden){const a=learningActive;const snap=JSON.parse(JSON.stringify(a));snap.status='interrupted';snap.finished_at=new Date().toISOString();snap.active_seconds=snap.time.answer_seconds+snap.time.explanation_seconds+snap.time.review_seconds;snap.correct_count=Object.values(snap.answers).filter(Boolean).length;snap.revision++;if(snap.profile_id)learningState.pending[a.attempt_id]=snap;learningSave();}else sendSharedStamp();}
  });
  window.addEventListener('online',()=>{learningIdentity();sendSharedStamp()});
  window.addEventListener('focus',learningIdentity);
  setTimeout(learningIdentity,100);

  const CM_MENU_CATALOG=[{"source_app": "soroban", "menu_id": "soroban:calculation:ba1", "name": "初級・足し算1｜1桁・繰り上がりなし", "category_key": "calculation", "skill_id": "soroban:add", "difficulty": "ba1", "difficulty_order": 1, "question_count": 12, "initial_estimate_seconds": 300, "estimate_basis": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": [], "next_menu_ids": ["soroban:calculation:ba2"], "target_age_min": null, "target_age_max": null, "selection_steps": ["チャレンジモード", "初級・足し算1｜1桁・繰り上がりなし"], "mode_kind": "challenge", "progression_group_id": "soroban:calculation:add"}, {"source_app": "soroban", "menu_id": "soroban:calculation:ba2", "name": "初級・足し算2｜1桁・繰り上がりあり", "category_key": "calculation", "skill_id": "soroban:add", "difficulty": "ba2", "difficulty_order": 2, "question_count": 12, "initial_estimate_seconds": 300, "estimate_basis": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": ["soroban:add"], "next_menu_ids": ["soroban:calculation:ba2x4"], "target_age_min": null, "target_age_max": null, "selection_steps": ["チャレンジモード", "初級・足し算2｜1桁・繰り上がりあり"], "mode_kind": "challenge", "progression_group_id": "soroban:calculation:add"}, {"source_app": "soroban", "menu_id": "soroban:calculation:ba2x4", "name": "初級・足し算3｜1桁の数を4つ足す", "category_key": "calculation", "skill_id": "soroban:add", "difficulty": "ba2x4", "difficulty_order": 3, "question_count": 12, "initial_estimate_seconds": 300, "estimate_basis": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": ["soroban:add"], "next_menu_ids": ["soroban:calculation:ba3"], "target_age_min": null, "target_age_max": null, "selection_steps": ["チャレンジモード", "初級・足し算3｜1桁の数を4つ足す"], "mode_kind": "challenge", "progression_group_id": "soroban:calculation:add"}, {"source_app": "soroban", "menu_id": "soroban:calculation:ba3", "name": "初級・足し算4｜2桁・繰り上がりなし", "category_key": "calculation", "skill_id": "soroban:add", "difficulty": "ba3", "difficulty_order": 4, "question_count": 12, "initial_estimate_seconds": 300, "estimate_basis": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": ["soroban:add"], "next_menu_ids": ["soroban:calculation:ba4"], "target_age_min": null, "target_age_max": null, "selection_steps": ["チャレンジモード", "初級・足し算4｜2桁・繰り上がりなし"], "mode_kind": "challenge", "progression_group_id": "soroban:calculation:add"}, {"source_app": "soroban", "menu_id": "soroban:calculation:ba4", "name": "初級・足し算5｜2桁・繰り上がりあり", "category_key": "calculation", "skill_id": "soroban:add", "difficulty": "ba4", "difficulty_order": 5, "question_count": 12, "initial_estimate_seconds": 300, "estimate_basis": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": ["soroban:add"], "next_menu_ids": ["soroban:calculation:ba4x4"], "target_age_min": null, "target_age_max": null, "selection_steps": ["チャレンジモード", "初級・足し算5｜2桁・繰り上がりあり"], "mode_kind": "challenge", "progression_group_id": "soroban:calculation:add"}, {"source_app": "soroban", "menu_id": "soroban:calculation:ba4x4", "name": "初級・足し算6｜2桁の数を4つ足す", "category_key": "calculation", "skill_id": "soroban:add", "difficulty": "ba4x4", "difficulty_order": 6, "question_count": 12, "initial_estimate_seconds": 300, "estimate_basis": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": ["soroban:add"], "next_menu_ids": ["soroban:calculation:ba5"], "target_age_min": null, "target_age_max": null, "selection_steps": ["チャレンジモード", "初級・足し算6｜2桁の数を4つ足す"], "mode_kind": "challenge", "progression_group_id": "soroban:calculation:add"}, {"source_app": "soroban", "menu_id": "soroban:calculation:ba5", "name": "初級・足し算7｜3桁の足し算", "category_key": "calculation", "skill_id": "soroban:add", "difficulty": "ba5", "difficulty_order": 7, "question_count": 12, "initial_estimate_seconds": 300, "estimate_basis": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": ["soroban:add"], "next_menu_ids": ["soroban:calculation:ba5x4"], "target_age_min": null, "target_age_max": null, "selection_steps": ["チャレンジモード", "初級・足し算7｜3桁の足し算"], "mode_kind": "challenge", "progression_group_id": "soroban:calculation:add"}, {"source_app": "soroban", "menu_id": "soroban:calculation:ba5x4", "name": "初級・足し算8｜3桁の数を4つ足す", "category_key": "calculation", "skill_id": "soroban:add", "difficulty": "ba5x4", "difficulty_order": 8, "question_count": 12, "initial_estimate_seconds": 300, "estimate_basis": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": ["soroban:add"], "next_menu_ids": [], "target_age_min": null, "target_age_max": null, "selection_steps": ["チャレンジモード", "初級・足し算8｜3桁の数を4つ足す"], "mode_kind": "challenge", "progression_group_id": "soroban:calculation:add"}, {"source_app": "soroban", "menu_id": "soroban:calculation:bs1", "name": "初級・引き算1｜1桁・繰り下がりなし", "category_key": "calculation", "skill_id": "soroban:sub", "difficulty": "bs1", "difficulty_order": 1, "question_count": 12, "initial_estimate_seconds": 300, "estimate_basis": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": [], "next_menu_ids": ["soroban:calculation:bs2"], "target_age_min": null, "target_age_max": null, "selection_steps": ["チャレンジモード", "初級・引き算1｜1桁・繰り下がりなし"], "mode_kind": "challenge", "progression_group_id": "soroban:calculation:sub"}, {"source_app": "soroban", "menu_id": "soroban:calculation:bs2", "name": "初級・引き算2｜1桁を引く・繰り下がりあり", "category_key": "calculation", "skill_id": "soroban:sub", "difficulty": "bs2", "difficulty_order": 2, "question_count": 12, "initial_estimate_seconds": 300, "estimate_basis": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": ["soroban:sub"], "next_menu_ids": ["soroban:calculation:bs2x4"], "target_age_min": null, "target_age_max": null, "selection_steps": ["チャレンジモード", "初級・引き算2｜1桁を引く・繰り下がりあり"], "mode_kind": "challenge", "progression_group_id": "soroban:calculation:sub"}, {"source_app": "soroban", "menu_id": "soroban:calculation:bs2x4", "name": "初級・引き算3｜2桁から1桁の数を3回引く", "category_key": "calculation", "skill_id": "soroban:sub", "difficulty": "bs2x4", "difficulty_order": 3, "question_count": 12, "initial_estimate_seconds": 300, "estimate_basis": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": ["soroban:sub"], "next_menu_ids": ["soroban:calculation:bs3"], "target_age_min": null, "target_age_max": null, "selection_steps": ["チャレンジモード", "初級・引き算3｜2桁から1桁の数を3回引く"], "mode_kind": "challenge", "progression_group_id": "soroban:calculation:sub"}, {"source_app": "soroban", "menu_id": "soroban:calculation:bs3", "name": "初級・引き算4｜2桁・繰り下がりなし", "category_key": "calculation", "skill_id": "soroban:sub", "difficulty": "bs3", "difficulty_order": 4, "question_count": 12, "initial_estimate_seconds": 300, "estimate_basis": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": ["soroban:sub"], "next_menu_ids": ["soroban:calculation:bs4"], "target_age_min": null, "target_age_max": null, "selection_steps": ["チャレンジモード", "初級・引き算4｜2桁・繰り下がりなし"], "mode_kind": "challenge", "progression_group_id": "soroban:calculation:sub"}, {"source_app": "soroban", "menu_id": "soroban:calculation:bs4", "name": "初級・引き算5｜2桁・繰り下がりあり", "category_key": "calculation", "skill_id": "soroban:sub", "difficulty": "bs4", "difficulty_order": 5, "question_count": 12, "initial_estimate_seconds": 300, "estimate_basis": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": ["soroban:sub"], "next_menu_ids": ["soroban:calculation:bs4x4"], "target_age_min": null, "target_age_max": null, "selection_steps": ["チャレンジモード", "初級・引き算5｜2桁・繰り下がりあり"], "mode_kind": "challenge", "progression_group_id": "soroban:calculation:sub"}, {"source_app": "soroban", "menu_id": "soroban:calculation:bs4x4", "name": "初級・引き算6｜2桁の数を4つ使う引き算", "category_key": "calculation", "skill_id": "soroban:sub", "difficulty": "bs4x4", "difficulty_order": 6, "question_count": 12, "initial_estimate_seconds": 300, "estimate_basis": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": ["soroban:sub"], "next_menu_ids": ["soroban:calculation:bs5"], "target_age_min": null, "target_age_max": null, "selection_steps": ["チャレンジモード", "初級・引き算6｜2桁の数を4つ使う引き算"], "mode_kind": "challenge", "progression_group_id": "soroban:calculation:sub"}, {"source_app": "soroban", "menu_id": "soroban:calculation:bs5", "name": "初級・引き算7｜3桁の引き算", "category_key": "calculation", "skill_id": "soroban:sub", "difficulty": "bs5", "difficulty_order": 7, "question_count": 12, "initial_estimate_seconds": 300, "estimate_basis": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": ["soroban:sub"], "next_menu_ids": ["soroban:calculation:bs5x4"], "target_age_min": null, "target_age_max": null, "selection_steps": ["チャレンジモード", "初級・引き算7｜3桁の引き算"], "mode_kind": "challenge", "progression_group_id": "soroban:calculation:sub"}, {"source_app": "soroban", "menu_id": "soroban:calculation:bs5x4", "name": "初級・引き算8｜3桁から2桁を4回引く", "category_key": "calculation", "skill_id": "soroban:sub", "difficulty": "bs5x4", "difficulty_order": 8, "question_count": 12, "initial_estimate_seconds": 300, "estimate_basis": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": ["soroban:sub"], "next_menu_ids": [], "target_age_min": null, "target_age_max": null, "selection_steps": ["チャレンジモード", "初級・引き算8｜3桁から2桁を4回引く"], "mode_kind": "challenge", "progression_group_id": "soroban:calculation:sub"}, {"source_app": "soroban", "menu_id": "soroban:calculation:mm1", "name": "中級・掛け算1｜1桁×1桁", "category_key": "calculation", "skill_id": "soroban:mul", "difficulty": "mm1", "difficulty_order": 1, "question_count": 12, "initial_estimate_seconds": 300, "estimate_basis": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": [], "next_menu_ids": ["soroban:calculation:mm2"], "target_age_min": null, "target_age_max": null, "selection_steps": ["チャレンジモード", "中級・掛け算1｜1桁×1桁"], "mode_kind": "challenge", "progression_group_id": "soroban:calculation:mul"}, {"source_app": "soroban", "menu_id": "soroban:calculation:mm2", "name": "中級・掛け算2｜2桁×1桁", "category_key": "calculation", "skill_id": "soroban:mul", "difficulty": "mm2", "difficulty_order": 2, "question_count": 12, "initial_estimate_seconds": 300, "estimate_basis": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": ["soroban:mul"], "next_menu_ids": ["soroban:calculation:mm3"], "target_age_min": null, "target_age_max": null, "selection_steps": ["チャレンジモード", "中級・掛け算2｜2桁×1桁"], "mode_kind": "challenge", "progression_group_id": "soroban:calculation:mul"}, {"source_app": "soroban", "menu_id": "soroban:calculation:mm3", "name": "中級・掛け算3｜2桁×2桁", "category_key": "calculation", "skill_id": "soroban:mul", "difficulty": "mm3", "difficulty_order": 3, "question_count": 12, "initial_estimate_seconds": 300, "estimate_basis": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": ["soroban:mul"], "next_menu_ids": [], "target_age_min": null, "target_age_max": null, "selection_steps": ["チャレンジモード", "中級・掛け算3｜2桁×2桁"], "mode_kind": "challenge", "progression_group_id": "soroban:calculation:mul"}, {"source_app": "soroban", "menu_id": "soroban:calculation:md1", "name": "中級・割り算1｜1〜81÷1桁", "category_key": "calculation", "skill_id": "soroban:div", "difficulty": "md1", "difficulty_order": 1, "question_count": 12, "initial_estimate_seconds": 300, "estimate_basis": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": [], "next_menu_ids": ["soroban:calculation:md2"], "target_age_min": null, "target_age_max": null, "selection_steps": ["チャレンジモード", "中級・割り算1｜1〜81÷1桁"], "mode_kind": "challenge", "progression_group_id": "soroban:calculation:div"}, {"source_app": "soroban", "menu_id": "soroban:calculation:md2", "name": "中級・割り算2｜3桁÷1桁", "category_key": "calculation", "skill_id": "soroban:div", "difficulty": "md2", "difficulty_order": 2, "question_count": 12, "initial_estimate_seconds": 300, "estimate_basis": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": ["soroban:div"], "next_menu_ids": ["soroban:calculation:md3"], "target_age_min": null, "target_age_max": null, "selection_steps": ["チャレンジモード", "中級・割り算2｜3桁÷1桁"], "mode_kind": "challenge", "progression_group_id": "soroban:calculation:div"}, {"source_app": "soroban", "menu_id": "soroban:calculation:md3", "name": "中級・割り算3｜3桁÷2桁", "category_key": "calculation", "skill_id": "soroban:div", "difficulty": "md3", "difficulty_order": 3, "question_count": 12, "initial_estimate_seconds": 300, "estimate_basis": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": ["soroban:div"], "next_menu_ids": [], "target_age_min": null, "target_age_max": null, "selection_steps": ["チャレンジモード", "中級・割り算3｜3桁÷2桁"], "mode_kind": "challenge", "progression_group_id": "soroban:calculation:div"}, {"source_app": "soroban", "menu_id": "soroban:calculation:a1", "name": "上級1｜4桁の足し算・引き算", "category_key": "calculation", "skill_id": "soroban:advanced", "difficulty": "a1", "difficulty_order": 1, "question_count": 12, "initial_estimate_seconds": 300, "estimate_basis": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": [], "next_menu_ids": ["soroban:calculation:a2"], "target_age_min": null, "target_age_max": null, "selection_steps": ["チャレンジモード", "上級1｜4桁の足し算・引き算"], "mode_kind": "challenge", "progression_group_id": "soroban:calculation:advanced"}, {"source_app": "soroban", "menu_id": "soroban:calculation:a2", "name": "上級2｜3桁×2桁 / 4桁÷2桁", "category_key": "calculation", "skill_id": "soroban:advanced", "difficulty": "a2", "difficulty_order": 2, "question_count": 12, "initial_estimate_seconds": 300, "estimate_basis": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": ["soroban:advanced"], "next_menu_ids": ["soroban:calculation:a3"], "target_age_min": null, "target_age_max": null, "selection_steps": ["チャレンジモード", "上級2｜3桁×2桁 / 4桁÷2桁"], "mode_kind": "challenge", "progression_group_id": "soroban:calculation:advanced"}, {"source_app": "soroban", "menu_id": "soroban:calculation:a3", "name": "上級3｜3桁×3桁 / 5桁÷3桁", "category_key": "calculation", "skill_id": "soroban:advanced", "difficulty": "a3", "difficulty_order": 3, "question_count": 12, "initial_estimate_seconds": 300, "estimate_basis": "仮設定：1問あたり25秒×12問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": ["soroban:advanced"], "next_menu_ids": [], "target_age_min": null, "target_age_max": null, "selection_steps": ["チャレンジモード", "上級3｜3桁×3桁 / 5桁÷3桁"], "mode_kind": "challenge", "progression_group_id": "soroban:calculation:advanced"}, {"source_app": "soroban", "menu_id": "soroban:hosu:add:1", "name": "足し算・初級", "category_key": "hosu", "skill_id": "soroban:complement:add", "difficulty": "add:1", "difficulty_order": 1, "question_count": 12, "initial_estimate_seconds": 480, "estimate_basis": "仮設定：1問あたり40秒×12問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": ["soroban:add"], "next_menu_ids": ["soroban:hosu:add:2"], "target_age_min": null, "target_age_max": null, "selection_steps": ["補数名人", "足し算・初級"], "mode_kind": "challenge", "progression_group_id": "soroban:hosu:add"}, {"source_app": "soroban", "menu_id": "soroban:hosu:add:2", "name": "足し算・中級", "category_key": "hosu", "skill_id": "soroban:complement:add", "difficulty": "add:2", "difficulty_order": 2, "question_count": 12, "initial_estimate_seconds": 600, "estimate_basis": "仮設定：1問あたり50秒×12問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": ["soroban:add"], "next_menu_ids": ["soroban:hosu:add:3"], "target_age_min": null, "target_age_max": null, "selection_steps": ["補数名人", "足し算・中級"], "mode_kind": "challenge", "progression_group_id": "soroban:hosu:add"}, {"source_app": "soroban", "menu_id": "soroban:hosu:add:3", "name": "足し算・上級", "category_key": "hosu", "skill_id": "soroban:complement:add", "difficulty": "add:3", "difficulty_order": 3, "question_count": 12, "initial_estimate_seconds": 720, "estimate_basis": "仮設定：1問あたり60秒×12問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": ["soroban:add"], "next_menu_ids": [], "target_age_min": null, "target_age_max": null, "selection_steps": ["補数名人", "足し算・上級"], "mode_kind": "challenge", "progression_group_id": "soroban:hosu:add"}, {"source_app": "soroban", "menu_id": "soroban:hosu:sub:1", "name": "引き算・初級", "category_key": "hosu", "skill_id": "soroban:complement:sub", "difficulty": "sub:1", "difficulty_order": 1, "question_count": 12, "initial_estimate_seconds": 480, "estimate_basis": "仮設定：1問あたり40秒×12問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": ["soroban:sub"], "next_menu_ids": ["soroban:hosu:sub:2"], "target_age_min": null, "target_age_max": null, "selection_steps": ["補数名人", "引き算・初級"], "mode_kind": "challenge", "progression_group_id": "soroban:hosu:sub"}, {"source_app": "soroban", "menu_id": "soroban:hosu:sub:2", "name": "引き算・中級", "category_key": "hosu", "skill_id": "soroban:complement:sub", "difficulty": "sub:2", "difficulty_order": 2, "question_count": 12, "initial_estimate_seconds": 600, "estimate_basis": "仮設定：1問あたり50秒×12問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": ["soroban:sub"], "next_menu_ids": ["soroban:hosu:sub:3"], "target_age_min": null, "target_age_max": null, "selection_steps": ["補数名人", "引き算・中級"], "mode_kind": "challenge", "progression_group_id": "soroban:hosu:sub"}, {"source_app": "soroban", "menu_id": "soroban:hosu:sub:3", "name": "引き算・上級", "category_key": "hosu", "skill_id": "soroban:complement:sub", "difficulty": "sub:3", "difficulty_order": 3, "question_count": 12, "initial_estimate_seconds": 720, "estimate_basis": "仮設定：1問あたり60秒×12問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": ["soroban:sub"], "next_menu_ids": [], "target_age_min": null, "target_age_max": null, "selection_steps": ["補数名人", "引き算・上級"], "mode_kind": "challenge", "progression_group_id": "soroban:hosu:sub"}, {"source_app": "soroban", "menu_id": "soroban:kuku:1", "name": "初級", "category_key": "kuku", "skill_id": "soroban:multiplication", "difficulty": "1", "difficulty_order": 1, "question_count": 10, "initial_estimate_seconds": 50, "estimate_basis": "仮設定：1問あたり5秒×10問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": [], "next_menu_ids": ["soroban:kuku:2"], "target_age_min": null, "target_age_max": null, "selection_steps": ["九九名人", "初級"], "mode_kind": "challenge", "progression_group_id": "soroban:kuku"}, {"source_app": "soroban", "menu_id": "soroban:kuku:2", "name": "中級", "category_key": "kuku", "skill_id": "soroban:multiplication", "difficulty": "2", "difficulty_order": 2, "question_count": 10, "initial_estimate_seconds": 50, "estimate_basis": "仮設定：1問あたり5秒×10問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": ["soroban:multiplication"], "next_menu_ids": ["soroban:kuku:3"], "target_age_min": null, "target_age_max": null, "selection_steps": ["九九名人", "中級"], "mode_kind": "challenge", "progression_group_id": "soroban:kuku"}, {"source_app": "soroban", "menu_id": "soroban:kuku:3", "name": "上級・完全ランダム10問", "category_key": "kuku", "skill_id": "soroban:multiplication", "difficulty": "3", "difficulty_order": 3, "question_count": 10, "initial_estimate_seconds": 50, "estimate_basis": "仮設定：1問あたり5秒×10問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": ["soroban:multiplication"], "next_menu_ids": ["soroban:kuku:4"], "target_age_min": null, "target_age_max": null, "selection_steps": ["九九名人", "上級・完全ランダム10問"], "mode_kind": "challenge", "progression_group_id": "soroban:kuku"}, {"source_app": "soroban", "menu_id": "soroban:kuku:4", "name": "特級・完全ランダム30問", "category_key": "kuku", "skill_id": "soroban:multiplication", "difficulty": "4", "difficulty_order": 4, "question_count": 30, "initial_estimate_seconds": 150, "estimate_basis": "仮設定：1問あたり5秒×30問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": ["soroban:multiplication"], "next_menu_ids": ["soroban:kuku:5"], "target_age_min": null, "target_age_max": null, "selection_steps": ["九九名人", "特級・完全ランダム30問"], "mode_kind": "challenge", "progression_group_id": "soroban:kuku"}, {"source_app": "soroban", "menu_id": "soroban:kuku:5", "name": "名人", "category_key": "kuku", "skill_id": "soroban:multiplication", "difficulty": "5", "difficulty_order": 5, "question_count": 90, "initial_estimate_seconds": 450, "estimate_basis": "仮設定：1問あたり5秒×90問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": ["soroban:multiplication"], "next_menu_ids": [], "target_age_min": null, "target_age_max": null, "selection_steps": ["九九名人", "名人"], "mode_kind": "challenge", "progression_group_id": "soroban:kuku"}, {"source_app": "soroban", "menu_id": "soroban:anzan:1", "name": "初級", "category_key": "anzan", "skill_id": "soroban:mental_arithmetic", "difficulty": "1", "difficulty_order": 1, "question_count": 10, "initial_estimate_seconds": 150, "estimate_basis": "仮設定：1問あたり15秒×10問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": [], "next_menu_ids": ["soroban:anzan:2"], "target_age_min": null, "target_age_max": null, "selection_steps": ["暗算名人", "初級"], "mode_kind": "challenge", "progression_group_id": "soroban:anzan"}, {"source_app": "soroban", "menu_id": "soroban:anzan:2", "name": "中級", "category_key": "anzan", "skill_id": "soroban:mental_arithmetic", "difficulty": "2", "difficulty_order": 2, "question_count": 10, "initial_estimate_seconds": 200, "estimate_basis": "仮設定：1問あたり20秒×10問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": [], "next_menu_ids": ["soroban:anzan:3"], "target_age_min": null, "target_age_max": null, "selection_steps": ["暗算名人", "中級"], "mode_kind": "challenge", "progression_group_id": "soroban:anzan"}, {"source_app": "soroban", "menu_id": "soroban:anzan:3", "name": "上級", "category_key": "anzan", "skill_id": "soroban:mental_arithmetic", "difficulty": "3", "difficulty_order": 3, "question_count": 10, "initial_estimate_seconds": 250, "estimate_basis": "仮設定：1問あたり25秒×10問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": [], "next_menu_ids": [], "target_age_min": null, "target_age_max": null, "selection_steps": ["暗算名人", "上級"], "mode_kind": "challenge", "progression_group_id": "soroban:anzan"}, {"source_app": "soroban", "menu_id": "soroban:tutorial:add1", "name": "1〜4をそのまま足す", "category_key": "calculation", "skill_id": "soroban:lesson:add1", "difficulty": "add1", "difficulty_order": 1, "question_count": 1, "initial_estimate_seconds": 90, "estimate_basis": "仮設定：1問あたり90秒×1問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": [], "next_menu_ids": ["soroban:tutorial:add2"], "target_age_min": null, "target_age_max": null, "selection_steps": ["珠の動きで学ぶ", "足し算", "1〜4をそのまま足す"], "mode_kind": "tutorial", "progression_group_id": "soroban:tutorial:add"}, {"source_app": "soroban", "menu_id": "soroban:tutorial:add2", "name": "5珠と1珠を組み合わせる", "category_key": "calculation", "skill_id": "soroban:lesson:add2", "difficulty": "add2", "difficulty_order": 2, "question_count": 1, "initial_estimate_seconds": 90, "estimate_basis": "仮設定：1問あたり90秒×1問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": ["soroban:lesson:add1"], "next_menu_ids": ["soroban:tutorial:add3"], "target_age_min": null, "target_age_max": null, "selection_steps": ["珠の動きで学ぶ", "足し算", "5珠と1珠を組み合わせる"], "mode_kind": "tutorial", "progression_group_id": "soroban:tutorial:add"}, {"source_app": "soroban", "menu_id": "soroban:tutorial:add3", "name": "5の補数で足す", "category_key": "calculation", "skill_id": "soroban:lesson:add3", "difficulty": "add3", "difficulty_order": 3, "question_count": 1, "initial_estimate_seconds": 90, "estimate_basis": "仮設定：1問あたり90秒×1問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": ["soroban:lesson:add2"], "next_menu_ids": ["soroban:tutorial:add4"], "target_age_min": null, "target_age_max": null, "selection_steps": ["珠の動きで学ぶ", "足し算", "5の補数で足す"], "mode_kind": "tutorial", "progression_group_id": "soroban:tutorial:add"}, {"source_app": "soroban", "menu_id": "soroban:tutorial:add4", "name": "10の補数で繰り上がる", "category_key": "calculation", "skill_id": "soroban:lesson:add4", "difficulty": "add4", "difficulty_order": 4, "question_count": 1, "initial_estimate_seconds": 90, "estimate_basis": "仮設定：1問あたり90秒×1問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": ["soroban:lesson:add3"], "next_menu_ids": ["soroban:tutorial:add5"], "target_age_min": null, "target_age_max": null, "selection_steps": ["珠の動きで学ぶ", "足し算", "10の補数で繰り上がる"], "mode_kind": "tutorial", "progression_group_id": "soroban:tutorial:add"}, {"source_app": "soroban", "menu_id": "soroban:tutorial:add5", "name": "2桁の繰り上がり", "category_key": "calculation", "skill_id": "soroban:lesson:add5", "difficulty": "add5", "difficulty_order": 5, "question_count": 1, "initial_estimate_seconds": 90, "estimate_basis": "仮設定：1問あたり90秒×1問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": ["soroban:lesson:add4"], "next_menu_ids": [], "target_age_min": null, "target_age_max": null, "selection_steps": ["珠の動きで学ぶ", "足し算", "2桁の繰り上がり"], "mode_kind": "tutorial", "progression_group_id": "soroban:tutorial:add"}, {"source_app": "soroban", "menu_id": "soroban:tutorial:sub1", "name": "そのまま引く", "category_key": "calculation", "skill_id": "soroban:lesson:sub1", "difficulty": "sub1", "difficulty_order": 1, "question_count": 1, "initial_estimate_seconds": 90, "estimate_basis": "仮設定：1問あたり90秒×1問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": [], "next_menu_ids": ["soroban:tutorial:sub2"], "target_age_min": null, "target_age_max": null, "selection_steps": ["珠の動きで学ぶ", "引き算", "そのまま引く"], "mode_kind": "tutorial", "progression_group_id": "soroban:tutorial:sub"}, {"source_app": "soroban", "menu_id": "soroban:tutorial:sub2", "name": "5珠から直接引く", "category_key": "calculation", "skill_id": "soroban:lesson:sub2", "difficulty": "sub2", "difficulty_order": 2, "question_count": 1, "initial_estimate_seconds": 90, "estimate_basis": "仮設定：1問あたり90秒×1問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": ["soroban:lesson:sub1"], "next_menu_ids": ["soroban:tutorial:sub3"], "target_age_min": null, "target_age_max": null, "selection_steps": ["珠の動きで学ぶ", "引き算", "5珠から直接引く"], "mode_kind": "tutorial", "progression_group_id": "soroban:tutorial:sub"}, {"source_app": "soroban", "menu_id": "soroban:tutorial:sub3", "name": "5の補数で引く", "category_key": "calculation", "skill_id": "soroban:lesson:sub3", "difficulty": "sub3", "difficulty_order": 3, "question_count": 1, "initial_estimate_seconds": 90, "estimate_basis": "仮設定：1問あたり90秒×1問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": ["soroban:lesson:sub2"], "next_menu_ids": ["soroban:tutorial:sub4"], "target_age_min": null, "target_age_max": null, "selection_steps": ["珠の動きで学ぶ", "引き算", "5の補数で引く"], "mode_kind": "tutorial", "progression_group_id": "soroban:tutorial:sub"}, {"source_app": "soroban", "menu_id": "soroban:tutorial:sub4", "name": "10の補数で繰り下がる", "category_key": "calculation", "skill_id": "soroban:lesson:sub4", "difficulty": "sub4", "difficulty_order": 4, "question_count": 1, "initial_estimate_seconds": 90, "estimate_basis": "仮設定：1問あたり90秒×1問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": ["soroban:lesson:sub3"], "next_menu_ids": ["soroban:tutorial:sub5"], "target_age_min": null, "target_age_max": null, "selection_steps": ["珠の動きで学ぶ", "引き算", "10の補数で繰り下がる"], "mode_kind": "tutorial", "progression_group_id": "soroban:tutorial:sub"}, {"source_app": "soroban", "menu_id": "soroban:tutorial:sub5", "name": "2桁の繰り下がり", "category_key": "calculation", "skill_id": "soroban:lesson:sub5", "difficulty": "sub5", "difficulty_order": 5, "question_count": 1, "initial_estimate_seconds": 90, "estimate_basis": "仮設定：1問あたり90秒×1問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": ["soroban:lesson:sub4"], "next_menu_ids": [], "target_age_min": null, "target_age_max": null, "selection_steps": ["珠の動きで学ぶ", "引き算", "2桁の繰り下がり"], "mode_kind": "tutorial", "progression_group_id": "soroban:tutorial:sub"}, {"source_app": "soroban", "menu_id": "soroban:tutorial:mul1", "name": "九九の答えを珠に置く", "category_key": "calculation", "skill_id": "soroban:lesson:mul1", "difficulty": "mul1", "difficulty_order": 1, "question_count": 1, "initial_estimate_seconds": 90, "estimate_basis": "仮設定：1問あたり90秒×1問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": [], "next_menu_ids": ["soroban:tutorial:mul2"], "target_age_min": null, "target_age_max": null, "selection_steps": ["珠の動きで学ぶ", "掛け算", "九九の答えを珠に置く"], "mode_kind": "tutorial", "progression_group_id": "soroban:tutorial:mul"}, {"source_app": "soroban", "menu_id": "soroban:tutorial:mul2", "name": "2桁×1桁の部分積", "category_key": "calculation", "skill_id": "soroban:lesson:mul2", "difficulty": "mul2", "difficulty_order": 2, "question_count": 1, "initial_estimate_seconds": 90, "estimate_basis": "仮設定：1問あたり90秒×1問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": ["soroban:lesson:mul1"], "next_menu_ids": ["soroban:tutorial:mul3"], "target_age_min": null, "target_age_max": null, "selection_steps": ["珠の動きで学ぶ", "掛け算", "2桁×1桁の部分積"], "mode_kind": "tutorial", "progression_group_id": "soroban:tutorial:mul"}, {"source_app": "soroban", "menu_id": "soroban:tutorial:mul3", "name": "2桁×2桁", "category_key": "calculation", "skill_id": "soroban:lesson:mul3", "difficulty": "mul3", "difficulty_order": 3, "question_count": 1, "initial_estimate_seconds": 90, "estimate_basis": "仮設定：1問あたり90秒×1問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": ["soroban:lesson:mul2"], "next_menu_ids": ["soroban:tutorial:mul4"], "target_age_min": null, "target_age_max": null, "selection_steps": ["珠の動きで学ぶ", "掛け算", "2桁×2桁"], "mode_kind": "tutorial", "progression_group_id": "soroban:tutorial:mul"}, {"source_app": "soroban", "menu_id": "soroban:tutorial:mul4", "name": "0がある数の位取り", "category_key": "calculation", "skill_id": "soroban:lesson:mul4", "difficulty": "mul4", "difficulty_order": 4, "question_count": 1, "initial_estimate_seconds": 90, "estimate_basis": "仮設定：1問あたり90秒×1問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": ["soroban:lesson:mul3"], "next_menu_ids": [], "target_age_min": null, "target_age_max": null, "selection_steps": ["珠の動きで学ぶ", "掛け算", "0がある数の位取り"], "mode_kind": "tutorial", "progression_group_id": "soroban:tutorial:mul"}, {"source_app": "soroban", "menu_id": "soroban:tutorial:div1", "name": "1桁÷1桁", "category_key": "calculation", "skill_id": "soroban:lesson:div1", "difficulty": "div1", "difficulty_order": 1, "question_count": 1, "initial_estimate_seconds": 90, "estimate_basis": "仮設定：1問あたり90秒×1問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": [], "next_menu_ids": ["soroban:tutorial:div2"], "target_age_min": null, "target_age_max": null, "selection_steps": ["珠の動きで学ぶ", "割り算", "1桁÷1桁"], "mode_kind": "tutorial", "progression_group_id": "soroban:tutorial:div"}, {"source_app": "soroban", "menu_id": "soroban:tutorial:div2", "name": "2桁÷1桁", "category_key": "calculation", "skill_id": "soroban:lesson:div2", "difficulty": "div2", "difficulty_order": 2, "question_count": 1, "initial_estimate_seconds": 90, "estimate_basis": "仮設定：1問あたり90秒×1問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": ["soroban:lesson:div1"], "next_menu_ids": ["soroban:tutorial:div3"], "target_age_min": null, "target_age_max": null, "selection_steps": ["珠の動きで学ぶ", "割り算", "2桁÷1桁"], "mode_kind": "tutorial", "progression_group_id": "soroban:tutorial:div"}, {"source_app": "soroban", "menu_id": "soroban:tutorial:div3", "name": "3桁÷1桁", "category_key": "calculation", "skill_id": "soroban:lesson:div3", "difficulty": "div3", "difficulty_order": 3, "question_count": 1, "initial_estimate_seconds": 90, "estimate_basis": "仮設定：1問あたり90秒×1問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": ["soroban:lesson:div2"], "next_menu_ids": ["soroban:tutorial:div4"], "target_age_min": null, "target_age_max": null, "selection_steps": ["珠の動きで学ぶ", "割り算", "3桁÷1桁"], "mode_kind": "tutorial", "progression_group_id": "soroban:tutorial:div"}, {"source_app": "soroban", "menu_id": "soroban:tutorial:div4", "name": "2桁で割る", "category_key": "calculation", "skill_id": "soroban:lesson:div4", "difficulty": "div4", "difficulty_order": 4, "question_count": 1, "initial_estimate_seconds": 90, "estimate_basis": "仮設定：1問あたり90秒×1問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": ["soroban:lesson:div3"], "next_menu_ids": [], "target_age_min": null, "target_age_max": null, "selection_steps": ["珠の動きで学ぶ", "割り算", "2桁で割る"], "mode_kind": "tutorial", "progression_group_id": "soroban:tutorial:div"}, {"source_app": "soroban", "menu_id": "soroban:kuku:read:1", "name": "1の段・読み上げ", "category_key": "kuku", "skill_id": "soroban:kuku:1", "difficulty": "read", "difficulty_order": 1, "question_count": 1, "initial_estimate_seconds": 30, "estimate_basis": "仮設定：1問あたり30秒×1問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": [], "next_menu_ids": [], "target_age_min": null, "target_age_max": null, "selection_steps": ["九九名人", "九九一覧表", "1の段の読み上げ"], "mode_kind": "reading", "progression_group_id": "soroban:kuku:reading"}, {"source_app": "soroban", "menu_id": "soroban:kuku:read:2", "name": "2の段・読み上げ", "category_key": "kuku", "skill_id": "soroban:kuku:2", "difficulty": "read", "difficulty_order": 2, "question_count": 1, "initial_estimate_seconds": 30, "estimate_basis": "仮設定：1問あたり30秒×1問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": [], "next_menu_ids": [], "target_age_min": null, "target_age_max": null, "selection_steps": ["九九名人", "九九一覧表", "2の段の読み上げ"], "mode_kind": "reading", "progression_group_id": "soroban:kuku:reading"}, {"source_app": "soroban", "menu_id": "soroban:kuku:read:3", "name": "3の段・読み上げ", "category_key": "kuku", "skill_id": "soroban:kuku:3", "difficulty": "read", "difficulty_order": 3, "question_count": 1, "initial_estimate_seconds": 30, "estimate_basis": "仮設定：1問あたり30秒×1問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": [], "next_menu_ids": [], "target_age_min": null, "target_age_max": null, "selection_steps": ["九九名人", "九九一覧表", "3の段の読み上げ"], "mode_kind": "reading", "progression_group_id": "soroban:kuku:reading"}, {"source_app": "soroban", "menu_id": "soroban:kuku:read:4", "name": "4の段・読み上げ", "category_key": "kuku", "skill_id": "soroban:kuku:4", "difficulty": "read", "difficulty_order": 4, "question_count": 1, "initial_estimate_seconds": 30, "estimate_basis": "仮設定：1問あたり30秒×1問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": [], "next_menu_ids": [], "target_age_min": null, "target_age_max": null, "selection_steps": ["九九名人", "九九一覧表", "4の段の読み上げ"], "mode_kind": "reading", "progression_group_id": "soroban:kuku:reading"}, {"source_app": "soroban", "menu_id": "soroban:kuku:read:5", "name": "5の段・読み上げ", "category_key": "kuku", "skill_id": "soroban:kuku:5", "difficulty": "read", "difficulty_order": 5, "question_count": 1, "initial_estimate_seconds": 30, "estimate_basis": "仮設定：1問あたり30秒×1問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": [], "next_menu_ids": [], "target_age_min": null, "target_age_max": null, "selection_steps": ["九九名人", "九九一覧表", "5の段の読み上げ"], "mode_kind": "reading", "progression_group_id": "soroban:kuku:reading"}, {"source_app": "soroban", "menu_id": "soroban:kuku:read:6", "name": "6の段・読み上げ", "category_key": "kuku", "skill_id": "soroban:kuku:6", "difficulty": "read", "difficulty_order": 6, "question_count": 1, "initial_estimate_seconds": 30, "estimate_basis": "仮設定：1問あたり30秒×1問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": [], "next_menu_ids": [], "target_age_min": null, "target_age_max": null, "selection_steps": ["九九名人", "九九一覧表", "6の段の読み上げ"], "mode_kind": "reading", "progression_group_id": "soroban:kuku:reading"}, {"source_app": "soroban", "menu_id": "soroban:kuku:read:7", "name": "7の段・読み上げ", "category_key": "kuku", "skill_id": "soroban:kuku:7", "difficulty": "read", "difficulty_order": 7, "question_count": 1, "initial_estimate_seconds": 30, "estimate_basis": "仮設定：1問あたり30秒×1問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": [], "next_menu_ids": [], "target_age_min": null, "target_age_max": null, "selection_steps": ["九九名人", "九九一覧表", "7の段の読み上げ"], "mode_kind": "reading", "progression_group_id": "soroban:kuku:reading"}, {"source_app": "soroban", "menu_id": "soroban:kuku:read:8", "name": "8の段・読み上げ", "category_key": "kuku", "skill_id": "soroban:kuku:8", "difficulty": "read", "difficulty_order": 8, "question_count": 1, "initial_estimate_seconds": 30, "estimate_basis": "仮設定：1問あたり30秒×1問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": [], "next_menu_ids": [], "target_age_min": null, "target_age_max": null, "selection_steps": ["九九名人", "九九一覧表", "8の段の読み上げ"], "mode_kind": "reading", "progression_group_id": "soroban:kuku:reading"}, {"source_app": "soroban", "menu_id": "soroban:kuku:read:9", "name": "9の段・読み上げ", "category_key": "kuku", "skill_id": "soroban:kuku:9", "difficulty": "read", "difficulty_order": 9, "question_count": 1, "initial_estimate_seconds": 30, "estimate_basis": "仮設定：1問あたり30秒×1問。実測による裏付けは未取得。", "estimate_kind": "provisional", "prerequisite_skill_ids": [], "next_menu_ids": [], "target_age_min": null, "target_age_max": null, "selection_steps": ["九九名人", "九九一覧表", "9の段の読み上げ"], "mode_kind": "reading", "progression_group_id": "soroban:kuku:reading"}];
  // chokomana.learning.v1 — immutable append-only event outbox, integer milliseconds.
  const CM_EVENTS_KEY='chokomana_soroban_events_v1',CM_LOCAL_KEY='chokomana_soroban_local_learner_v1';
  let cmLocal=safeRead(CM_LOCAL_KEY,null);if(!cmLocal){cmLocal=stampUuid();safeWrite(CM_LOCAL_KEY,cmLocal)}
  const cmWindow=stampUuid(),cmSegment=stampUuid();let cmSequence=0;
  let cmStorageFailed=false;
  let cmEvents=safeRead(CM_EVENTS_KEY,{pending:{},acked:{},archive:{}});
  if(!cmEvents.pending||!cmEvents.acked)cmEvents={pending:{},acked:{},archive:{}};
  cmEvents.archive=cmEvents.archive||{};
  function cmPersist(){
    const disk=safeRead(CM_EVENTS_KEY,{pending:{},acked:{},archive:{}});
    cmEvents.archive={...(disk.archive||{}),...cmEvents.archive};cmEvents.acked={...disk.acked,...cmEvents.acked};cmEvents.pending={...disk.pending,...cmEvents.pending};
    for(const id of Object.keys(cmEvents.acked))delete cmEvents.pending[id];
    const lastAttempt=Object.values(cmEvents.archive).at(-1)?.attempt_id;for(const [id,e] of Object.entries(cmEvents.archive))if(e.attempt_id!==lastAttempt&&cmEvents.acked[id]&&!cmEvents.pending[id])delete cmEvents.archive[id];
    if(!safeWrite(CM_EVENTS_KEY,cmEvents)){cmStorageFailed=true;const el=$('#chokomanaLinkStatus');if(el)el.textContent='記録を端末に保存できません。学習は続けられますが、ページを閉じると未送信記録が失われることがあります。';return false}return true;
  }
  function cmEmit(a,type,payload,q=null,eventId=null){
    if(!a)return null;const id=eventId||stampUuid();if(!id)return null;
    const event={schema_version:1,event_id:id,profile_id:a.profile_id||null,source_app:'soroban',app_version:'CLEAN-V171-DAILY-MEDAL-POPUP',content_version:'soroban-material-167',attempt_id:a.attempt_id,occurrence_id:q?.occurrence_id||null,question_id:q?.problem_id||null,segment_id:cmSegment,sequence:++cmSequence,occurred_at:new Date().toISOString(),event_type:type,payload:JSON.parse(JSON.stringify(payload))};
    cmEvents.pending[id]=event;cmEvents.archive[id]=event;cmPersist();return id;
  }
  function cmInput(kind=null){return kind==='speech'?'speech':kind==='button'?'choice':cmLastInput;}
  let cmLastInput='other',cmNextLaunch=null;
  root.addEventListener('click',e=>{const b=e.target.closest('button');const kind=({kukuRetryBtn:'kuku',hosuRetryBtn:'hosu',anzanRetryBtn:'anzan',retryBtn:'calculation',restartChallengeBtn:'calculation'})[b?.id];if(kind){const previous=Object.values(learningState.attempts).filter(a=>a.category_key===kind).at(-1);cmNextLaunch={kind,parent_attempt_id:previous?.attempt_id||null};}},true);
  root.addEventListener('pointerup',e=>{if(e.target.closest('#keypad,#kukuKeypad,#anzanKeypad,#hosuDigits'))cmLastInput='keypad';else if(e.target.closest('button'))cmLastInput='choice'},true);
  root.addEventListener('keydown',()=>{cmLastInput='keyboard';learningTick();if(learningClock)learningClock.cmPhase='answering'},true);
  function cmSettings(a){return {voice_enabled:a.category_key==='hosu'?Boolean(hosu.voice):a.category_key==='kuku'?Boolean(kukuVoiceEnabled):a.category_key==='anzan'?Boolean(anzanVoiceEnabled):Boolean(voiceAnswerEnabled),display_age:null,kanji_grade:null,time_limit_seconds:a.category_key==='calculation'?300:null,flash_interval_ms:a.category_key==='anzan'?anzanSpeedInfo().delay||null:null,input_method:cmLastInput,voice_rate:1.0,narration_enabled:a.cmMenu?.mode_kind==='tutorial'?Boolean(learningVoiceEnabled):a.cmMenu?.mode_kind==='reading'?true:a.category_key==='hosu'?true:null,voice_answer_enabled:a.category_key==='kuku'?Boolean(kukuVoiceEnabled):a.category_key==='hosu'?Boolean(hosu.voice):a.category_key==='anzan'?Boolean(anzanVoiceEnabled):Boolean(voiceAnswerEnabled)};}
  function cmStart(a){if(a.legacy_source&&!a.cmLegacyImported){cmEmit(a,'legacy_import',a.legacy_source,null,a.attempt_id);a.cmLegacyImported=true;}if(a.cmStarted){if(a.cmSegment!==cmSegment){a.cmSegment=cmSegment;cmEmit(a,'session_resumed',{reason:'page_reload',suspended_occurrence_id:null,last_response_id:null});}return;}a.cmStarted=true;a.cmSegment=cmSegment;const menu=CM_MENU_CATALOG.find(m=>m.menu_id===a.menu_id);a.cmMenu=menu;const launch=cmNextLaunch?.kind===a.category_key?cmNextLaunch:null;cmNextLaunch=null;
    cmEmit(a,'session_started',{menu_id:a.menu_id,category_id:a.category_key,difficulty_id:menu?.difficulty||a.difficulty,progression_group_id:menu?.progression_group_id||a.skill_id,mode:menu?.mode_kind==='tutorial'?'learn':menu?.mode_kind==='reading'?'reading_aloud':a.assignment_context?.remedial_skill_id?'drill':a.assignment_context?.weakness_mode?'review':'challenge',original_mode:a.difficulty,planned_question_count:a.total_count,settings_snapshot:cmSettings(a),trigger:launch?'retry':a.assignment_context?.remedial_skill_id||a.assignment_context?.weakness_mode?'remedial':'free',plan_item_id:null,parent_attempt_id:launch?.parent_attempt_id||null,local_learner_id:cmLocal,identity_link_version:a.profile_id?'launch-ticket-device-v1':null});}
  function cmPresent(a,q,source){
    if(q.occurrence_id)return;q.occurrence_id=stampUuid();q.cmResponseCount=0;q.cmSupport={hint_count:0,max_hint_step:null,explanation_seen:false,answer_seen:false,worked_example_seen:false,parent_help:null};q.cmSnapshot=source;
    const tutorial=a.cmMenu?.mode_kind==='tutorial',reading=a.cmMenu?.mode_kind==='reading';
    if(tutorial){q.cmSupport.worked_example_seen=true;q.cmSupport.answer_seen=true;}
    if(reading){q.cmSupport.answer_seen=true;q.cmSupport.explanation_seen=true;}
    const terms=source.terms||[source.a,source.b];
    let complementBases=null,carry=null,borrow=null;
    if(a.category_key==='hosu'){complementBases=[...new Set((source.events||[]).filter(e=>e.kind==='question').map(e=>e.base))];carry=source.op==='＋'&&complementBases.includes(10);borrow=source.op==='－'&&complementBases.includes(10);}
    else if(a.category_key==='calculation'&&typeof source.a==='number'&&['＋','－'].includes(source.op)){
      try{const plans=[];const nums=questionTerms(source),ops=questionOperators(source);let v=nums[0];for(let i=0;i<ops.length;i++){if(['＋','－'].includes(ops[i]))plans.push(buildHosuPlan(v,ops[i],nums[i+1]));v=calculate(v,ops[i],nums[i+1]);}const ev=plans.flatMap(p=>p.events).filter(e=>e.kind==='question');complementBases=[...new Set(ev.map(e=>e.base))];carry=ev.some(e=>e.base===10&&e.sign>0);borrow=ev.some(e=>e.base===10&&e.sign<0);}catch(e){}
    }
    const axes={operand_digits:terms.map(v=>typeof v==='object'?String(v.value).length:typeof v==='number'?String(v).length:null),term_count:terms.length,operators:source.operators||source.op||null,complement_bases:complementBases,carry,borrow,flash_interval_ms:a.category_key==='anzan'?anzanSpeedInfo().delay||null:null};
    cmEmit(a,'item_presented',{question_family_id:q.variant_group,skill_ids:q.skill_ids,question_content_version:a.content_version,position:q.question_order,presentation_kind:source.isWeakness?'scheduled_repeat':'new',seen_in_local_history:q.same_problem_seen,parent_occurrence_id:null,retry_index:0,answer_exposed_before:tutorial||reading,support_snapshot:q.cmSupport,item_settings:axes,choice_order:source.quiz?.options?.map(v=>'choice:'+String(v))||source.choice_ids||null,input_method:cmInput(),question_snapshot:source,lifetime_first_seen:'unknown',assessment_method:reading?'unscored':'automatic'},q);
    if(tutorial)cmSupport(a,q,'worked_example',null,null,true);
  }
  function cmSupport(a,q,type,substep=null,step=null,revealing=false){if(!q)return;const before=!(q.cmResponseCount>0);const s=q.cmSupport;
    if(type==='hint'){s.hint_count++;s.max_hint_step=step;}if(type==='explanation')s.explanation_seen=true;if(type==='answer')s.answer_seen=true;if(type==='worked_example')s.worked_example_seen=true;
    cmEmit(a,'support_used',{support_type:type,substep_id:substep,step,support_id:a.menu_id+':'+type,support_version:a.content_version,before_first_response:before,answer_revealing:revealing,requested_at:new Date().toISOString()},q);
  }
  function cmResponse(a,q,ok,value,substep=null,input=null,status='answered',expected=null){if(!q)return;const r=stampUuid();q.cmResponseCount=(q.cmResponseCount||0)+1;
    const active=q.time.answer_seconds*1000;
    let observedSkills=null;if(a.category_key==='hosu'&&substep){const source=q.cmSnapshot?.events?.[Number(String(substep).split(':')[0])];if(source?.base)observedSkills=['soroban:complement:'+source.base];}else if(String(substep||'').startsWith('hint:'))observedSkills=['soroban:complement:10'];
    cmEmit(a,'response_submitted',{response_id:r,skill_ids:observedSkills,observation_scope:observedSkills?'substep':'whole_item_unlocalized',response_index:q.cmResponseCount,substep_id:substep==='answer'?null:substep,response_value:value===undefined?null:value,response_status:status,input_method:cmInput(input),assessment_method:a.cmMenu?.mode_kind==='reading'?'unscored':'automatic',is_correct:status==='answered'?Boolean(ok):null,correctness_basis:'existing_app_evaluator',rubric_id:a.menu_id,rubric_version:a.content_version,evaluator_version:'soroban-163',support_before_response:{...q.cmSupport},answer_latency_ms:Number.isFinite(active)?Math.round(active):null,timing_quality:a.timing_quality==='measured'?'complete':'partial',speech_status:cmInput(input)==='speech'?'recognized':'not_used',supersedes_response_id:null,reason_response:null,observed_error_code:null,inferred_error:null,expected_value:expected},q);
    q.last_response_id=r;return r;
  }
  function cmInterval(a,c,elapsed,startAt,endAt,bucket){if(elapsed<=0)return;const excluded={hidden:0,explicit_pause:0,blocking_wait:0};let active=Math.round(elapsed*1000),quality='complete',reason=null;
    if(bucket==='hidden_seconds'){excluded.hidden=active;active=0;reason='tab_hidden'}else if(bucket==='break_seconds'){excluded.explicit_pause=active;active=0;reason='explicit_pause'}else if(bucket==='network_wait_seconds'){excluded.blocking_wait=active;active=0;reason='blocking_wait'}else if(bucket==='unmeasured_seconds'){active=null;quality='unknown';reason='not_available'}
    if(a.timing_quality==='clock_changed'){active=null;quality='unknown';reason='wall_clock_changed'}
    if(a.timing_quality==='contended'){active=null;quality='unknown';reason='other_window'}
    const phase=c.cmPhase||({answer:'thinking',explanation:'explanation',review:'feedback',unmeasured:'other',network_wait:'other'}[c.phase]||'other');
    cmEmit(a,'time_interval_closed',{phase:a.cmMenu?.mode_kind==='reading'?'reading_aloud':phase,start_at:startAt,end_at:endAt,elapsed_ms:Math.round(elapsed*1000),active_ms:active,excluded_ms:excluded,exclusion_reason:reason,timing_quality:quality,window_instance_id:cmWindow,substep_id:c.substep||null},a.questions[String(c.index)]);
  }
  function cmEnd(a,status){if(!a.cmStarted)cmStart(a);cmEmit(a,'session_ended',{status,planned_question_count:a.total_count,presented_count:Object.keys(a.questions).length,answered_count:Object.values(a.questions).filter(q=>q.cmResponseCount>0).length,last_occurrence_id:Object.values(a.questions).at(-1)?.occurrence_id||null,last_response_id:Object.values(a.questions).at(-1)?.last_response_id||null,original_result:{correct_count:Object.values(a.answers).filter(Boolean).length,total_count:a.total_count,grade:a.grade||null}},Object.values(a.questions).at(-1));}

  // Administrator export without adding a child-facing control or mixing performance logs.
  window.__chokomanaExportSession=(attemptId=null)=>{
    const all=Object.values(cmEvents.archive),id=attemptId||all.at(-1)?.attempt_id;
    const data={specification_id:'chokomana.learning.v1',source_app:'soroban',attempt_id:id||null,events:all.filter(e=>e.attempt_id===id),pending_event_ids:Object.keys(cmEvents.pending).filter(k=>cmEvents.pending[k].attempt_id===id)};
    const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'}),link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download='chokomana_soroban_'+(id||'empty')+'.json';link.click();URL.revokeObjectURL(link.href);return data;
  };
  $('#chokomanaExportBtn').addEventListener('click',()=>window.__chokomanaExportSession());

  window.parent.postMessage({isStreamlitMessage:true,type:'streamlit:componentReady',apiVersion:1},'*');
  // Fit every screen to its intrinsic content; never use the iframe viewport as a minimum.
  let appFrameHeight = null;
  let appFrameHeightScheduled = false;
  function syncAppFrameHeight() {
    appFrameHeightScheduled = false;
    const bounds = root.getBoundingClientRect();
    const scrollTop = window.scrollY || document.documentElement.scrollTop || 0;
    // root includes normal-flow children and padding. scrollHeight/body height would
    // retain the previous iframe height and prevent short pages from shrinking.
    const height = Math.max(1, Math.ceil(bounds.bottom + scrollTop + 8));
    if (!Number.isFinite(height) || height === appFrameHeight) return;
    appFrameHeight = height;
    window.parent.postMessage({isStreamlitMessage:true,type:'streamlit:setFrameHeight',height},'*');
  }
  function scheduleAppFrameHeight() {
    if (appFrameHeightScheduled) return;
    appFrameHeightScheduled = true;
    requestAnimationFrame(syncAppFrameHeight);
  }
  if (typeof ResizeObserver !== "undefined") {
    new ResizeObserver(scheduleAppFrameHeight).observe(root);
  }
  if (typeof MutationObserver !== "undefined") {
    new MutationObserver(scheduleAppFrameHeight).observe(root, {
      attributes:true,attributeFilter:["class","style","hidden","open"],
      childList:true,subtree:true,characterData:true
    });
  }
  root.addEventListener("toggle", scheduleAppFrameHeight, true);
  root.addEventListener("load", scheduleAppFrameHeight, true);
  window.addEventListener("resize", scheduleAppFrameHeight);
  if (document.fonts?.ready) document.fonts.ready.then(scheduleAppFrameHeight);
  syncAppFrameHeight();

  function finishHosuMode() {
    stopHosuSession();
    const key = `${hosu.op}|${hosu.level}`;
    if (!hosu.recorded) {
      completeSharedStamp(hosuStampAttempt,gradeSharedScore(hosu.correct,12));
      const previous = hosu.stats[key] || {};
      hosu.stats[key] = {
        sessions: (Number(previous.sessions) || 0) + 1,
        best: Math.max(Number(previous.best) || 0, hosu.correct),
        lastCorrect: hosu.correct, lastAt: new Date().toISOString()
      };
      try { localStorage.setItem(HOSU_STORAGE_KEY, JSON.stringify(hosu.stats)); } catch (error) {}
      hosu.recorded = true;
    }
    $("#hosuGame").classList.add("hidden");
    $("#hosuResult").classList.remove("hidden");
    $("#hosuResultScore").textContent = `${hosu.correct} / 12`;
    $("#hosuResultText").textContent = `すべての補数を最初に答えられた問題 ${hosu.correct}問｜再挑戦 ${hosu.mistakeQuestions}問｜ヒント使用 ${hosu.hintQuestions}問`;
    $("#hosuSessionCount").textContent = `このモードの挑戦 ${hosu.stats[key].sessions}回目`;
    speakHosu(`12問おわりました。自力で正解できた問題は${hosu.correct}問です。`);
  }

  $("#hosuNextBtn").addEventListener("click", nextHosuStep);
  $("#hosuMenuBtn").addEventListener("click", showHosuHome);
  $("#hosuResultMenuBtn").addEventListener("click", showHosuHome);
  $("#hosuRetryBtn").addEventListener("click", () => startHosuMode(hosu.op, hosu.level));
  $("#hosuBaseChoices").addEventListener("click", (event) => {
    const button = event.target.closest("[data-hosu-base]");
    if (button) submitHosuAnswer(button.dataset.hosuBase);
  });
  $("#hosuDigits").addEventListener("click", (event) => {
    const button = event.target.closest("[data-hosu-digit]");
    if (button) submitHosuAnswer(button.dataset.hosuDigit);
  });
  $("#hosuHintBtn").addEventListener("click", () => {
    const event = hosu.questions[hosu.index]?.events[hosu.position];
    if (event?.kind !== "question" || hosu.complete) return;
    learningHint(hosuStampAttempt,hosu.index);
    hosu.questionHint = true;
    const explanation = hosuComplementReason(event);
    $("#hosuExplanation").textContent = explanation;
    $("#hosuExplanation").classList.remove("hidden");
    speakHosu(explanation);
  });
  $("#hosuVoiceBtn").addEventListener("click", () => {
    hosu.voice = !hosu.voice && Boolean(getSpeechRecognitionClass());
    updateHosuVoiceUi();
    stopHosuRecognition();
    if (!hosu.resolved) renderHosuStep(true);
    if (!getSpeechRecognitionClass()) {
      $("#hosuVoiceStatus").textContent = "このブラウザでは音声回答を使えません。数字とボタンで進めてね。";
    }
  });

  const BGM_SETTING_KEY = "soroban_bgm_enabled_v1";
  const VOICE_DEFAULT_SETTING_KEY = "soroban_voice_answer_default_v1";
  const LEARNING_VOICE_SETTING_KEY = "soroban_learning_voice_default_v1";
  const ANZAN_SPEED_SETTING_KEY = "soroban_anzan_speed_v1";
  const ANALYSIS_VIDEO_SETTING_KEY = "soroban_analysis_video_v1";

  let preferredVoiceAnswerEnabled = false;
  let preferredLearningVoiceEnabled = false;
  let anzanSpeed = "slow";
  let analysisVideoEnabled = false;

  let pendingVideoMode = null;
  let analysisCameraStream = null;
  let sessionMediaRecorder = null;
  let sessionVideoChunks = [];
  let sessionVideoBlob = null;
  let sessionVideoUrl = null;
  let sessionVideoMimeType = "";
  let sessionVideoStartedAtPerf = null;
  let sessionVideoStartedAtIso = null;
  let sessionVideoDurationMs = 0;
  let sessionVideoActive = false;
  let sessionVideoDiscardOnStop = false;
  let sessionVideoMode = null;
  let sessionQuestionMarks = [];
  let reviewClipEndSec = null;

  const KUKU_TOTAL_QUESTIONS = 10;
  const KUKU_MEDAL_STORAGE_KEY = "soroban_kuku_medal_counts_v1";
  const KUKU_MEDAL_DEFS = Object.freeze([
    { key: "gold", label: "金", minRate: 0.95 },
    { key: "silver", label: "銀", minRate: 0.90 },
    { key: "bronze", label: "銅", minRate: 0.80 }
  ]);
  let kukuLevel = 1;
  let kukuQuestions = [];
  let kukuQuestionIndex = 0;
  let kukuCorrect = 0;
  let kukuStreak = 0;
  let kukuAnswerBuffer = "";
  let kukuLocked = true;
  let kukuSeconds = 0;
  let kukuTimerHandle = null;
  let kukuRecognition = null;
  let kukuListening = false;
  let kukuSpeechDetected = false;
  let kukuPromptSpeaking = false;
  let kukuVoiceEnabled = false;
  let kukuRunToken = 0;

  // 九九の制限時間は、子どもが実際に発声している時間だけ進める。
  let kukuRemainingMs = 0;
  let kukuSpeechStartedAt = 0;

  const ANZAN_TOTAL_QUESTIONS = 10;
  let anzanLevel = 1;
  let anzanQuestionIndex = 0;
  let anzanCorrect = 0;
  let anzanQuestion = null;
  let anzanAnswerBuffer = "";
  let anzanRunToken = 0;
  let anzanRecognition = null;
  let anzanVoiceEnabled = false;
  let anzanVoiceBlocked = false;
  let anzanVoicePending = false;
  let anzanRecognitionTimer = null;
  let anzanVoiceSubmitTimer = null;
  let anzanListening = false;
  let anzanListeningStartedAt = 0;
  let anzanSpeechDetected = false;
  let anzanLocked = false;

  const RULES = Object.freeze({
    addSubOperandMin: 1,
    subtractionMinAnswer: 0,
    divisionMustBeInteger: true
  });

  const TOTAL_QUESTIONS = 12;

  // =====================================================
  // 自動レベルアップ・苦手克服
  // =====================================================
  const LEARNING_STORAGE_KEY = "soroban_learning_stats_v1";
  const RANKING_STORAGE_KEY = "soroban_score_rankings_v2";
  const CHALLENGE_COUNT_STORAGE_KEY = "soroban_challenge_counts_v1";
  const CHALLENGE_MEDAL_STORAGE_KEY = "soroban_challenge_medal_counts_v1";
  const SESSION_HISTORY_STORAGE_KEY = "soroban_session_history_v1";
  const RANK_CERTIFICATION_STORAGE_KEY = "soroban_rank_certification_v2";
  const CHALLENGE_RESUME_STORAGE_KEY = "soroban_challenge_resume_v2";
  const CHALLENGE_CURRICULUM_VERSION = "split-cumulative-rank-tracks-v1";
  const MAX_SESSION_HISTORY = 200;
  const MAX_RANKING_ENTRIES_PER_MODE = 100;

  // 最初の5問（1〜5問目）には苦手克服問題を入れない。
  // その後の7問の中へ、最大5問を分散して入れる。
  const WEAKNESS_SLOTS = new Set([5, 6, 8, 9, 11]);

  // 苦手克服問題として1回正解した時点で克服扱い。
  // 一度克服した問題は、それ以降の苦手克服枠には出さない。
  const RECOVERY_STREAK_TO_MASTER = 1;

  // 同じ種類の学習内でのみ自動レベルアップする。
  const NEXT_MODE = Object.freeze({
    ba1: "ba2",
    ba2: "ba2x4",
    ba2x4: "ba3",
    ba3: "ba4",
    ba4: "ba4x4",
    ba4x4: "ba5",
    ba5: "ba5x4",
    bs1: "bs2",
    bs2: "bs2x4",
    bs2x4: "bs3",
    bs3: "bs4",
    bs4: "bs4x4",
    bs4x4: "bs5",
    bs5: "bs5x4",
    mm1: "mm2",
    mm2: "mm3",
    md1: "md2",
    md2: "md3",
    a2: "a3"
  });

  let currentMode = null;
  let sessionTotalQuestions = TOTAL_QUESTIONS;
  let activeWeaknessChallengeMode = null;
  let questions = [];
  let index = 0;
  let score = 0;
  let answers = [];
  let seconds = 300;
  let timerHandle = null;
  // 5分計測は常時有効。0:00になっても強制終了しない。
  let timeLimitEnabled = true;
  let timeDisplayEnabled = true;
  let locked = false;
  let correctStreak = 0;
  let maxCorrectStreak = 0;
  let scoreAnimationToken = 0;
  let bgmOn = true;
  let currentBgm = null;
  let currentBgmGroupKey = null;

  let learningStats = loadLearningStats();
  let scoreRankings = loadScoreRankings();
  let challengeCounts = loadChallengeCounts();
  let kukuMedalStats = loadKukuMedalStats();
  let challengeMedalStats = loadChallengeMedalStats();
  let sessionChallengeMedalAwarded = false;
  let sessionChallengeMedalTier = null;
  let sessionHistory = loadSessionHistory();
  let sessionWeakAsked = 0;
  let sessionWeakCorrect = 0;
  let promotedMode = null;
  let sessionRankingSaved = false;
  let sessionChallengeRecorded = false;
  let sessionHistorySaved = false;
  let activeRemedialSkillId = null;
  let questionTimingLog = [];
  let rankingModalMode = null;

  let inAppBackGuardReady = false;
  let handlingBrowserBack = false;

  let hintRunToken = 0;
  let hintDigitCount = 1;
  let hintRods = [];
  let hintManualSteps = [];
  let hintManualIndex = 0;

  let voiceAnswerEnabled = false;
  let voiceRecognition = null;
  let voiceRecognitionRunning = false;
  let voicePauseForFeedback = false;
  let voiceCalloutRunning = false;
  let voiceRestartTimer = null;
  let voiceListeningStartedAt = 0;
  let voiceSpeechDetected = false;

  // 「ゴワサン」は1問につき1回だけ。
  // 音声認識が無音で切れても、この番号が同じ間は言い直さない。
  let gowasanSpokenForIndex = -1;

  // 珠ヒントの音声解説中は、回答用マイクを止める。
  let hintNarrationActive = false;
  let hintNarrationToken = 0;
  let hintQuestionRecognition = null;
  let hintQuestionListening = false;
  let hintQuestionListeningStartedAt = 0;
  let hintQuestionSpeechDetected = false;
  let hintQuestionRetryTimer = null;
  let hintAutoAnimating = false;

  // 「ゴワサン！」の直後だけ短く余韻を待つ。
  // 問題を解いている間はBGMを止めない。
  const MIC_PRE_SILENCE_MS = 450;
  const MIC_RESULT_GUARD_MS = 350;
  const HINT_MIC_AFTER_TTS_MS = 70;
  const HINT_MIC_RETRY_MS = 180;

  const BGM_VOLUME_NORMAL = 0.68;
  const BGM_VOLUME_APP_SPEECH = 0.09;
  // 九九チャレンジは音声回答を優先するため、通常時もBGMを小さめにする。
  const BGM_VOLUME_KUKU_NORMAL = 0.30;
  // 九九の問題発声中とマイク待機中は、声を最優先してBGMを止める。
  const BGM_VOLUME_KUKU_PROMPT = 0.00;
  const BGM_VOLUME_LISTENING = 0.00;

  let bgmKeepAliveTimer = null;

  class BgmEngine {
    constructor(urls) {
      this.urls = urls;
      this.ctx = null;
      this.masterGain = null;
      this.buffers = new Map();

      this.currentName = null;
      this.currentSource = null;
      this.currentSourceGain = null;

      this.playGeneration = 0;
      this.targetVolume = BGM_VOLUME_NORMAL;
    }

    ensureContext() {
      const AudioContextClass =
        window.AudioContext ||
        window.webkitAudioContext;

      if (!AudioContextClass) {
        return false;
      }

      if (!this.ctx) {
        this.ctx = new AudioContextClass({
          latencyHint: "interactive"
        });

        this.masterGain =
          this.ctx.createGain();

        this.masterGain.gain.value =
          this.targetVolume;

        // 音声認識中の自動音量調整と、利用者の音量設定を別のGainで合成。
        this.appVolumeOutput = connectAppAudioOutput(this.ctx, this.masterGain);
      }

      // resume() は非同期だが、ここでは呼び出し自体を
      // ユーザー操作と同じイベント内で開始する。
      if (this.ctx.state !== "running") {
        this.ctx.resume().catch(() => {});
      }

      return true;
    }

    async ensureRunning() {
      if (!this.ensureContext()) {
        return false;
      }

      if (this.ctx.state !== "running") {
        try {
          await this.ctx.resume();
        } catch (error) {
          return false;
        }
      }

      return this.ctx.state === "running";
    }

    setVolume(value, rampSeconds = 0.12) {
      this.targetVolume = value;

      if (
        !this.ctx ||
        !this.masterGain
      ) {
        return;
      }

      const now = this.ctx.currentTime;
      const gain = this.masterGain.gain;

      gain.cancelScheduledValues(now);
      gain.setValueAtTime(
        Math.max(0.0001, gain.value),
        now
      );
      gain.linearRampToValueAtTime(
        value,
        now + rampSeconds
      );
    }

    async loadBuffer(name) {
      if (this.buffers.has(name)) {
        return this.buffers.get(name);
      }

      const url = this.urls[name];

      if (!url) {
        throw new Error(
          `BGM URLがありません: ${name}`
        );
      }

      const ready =
        await this.ensureRunning();

      if (!ready) {
        throw new Error(
          "Web Audioを開始できません。"
        );
      }

      const downloadDone = appDiagnostics.span("bgm_download", {track:name});
      let decoded;
      try {
      const response = await fetch(
        url,
        {
          method: "GET",
          cache: "force-cache",
          mode: "cors"
        }
      );

      if (!response.ok) {
        throw new Error(
          `BGM取得失敗: ${response.status}`
        );
      }

      const arrayBuffer =
        await response.arrayBuffer();

      downloadDone();
      const decodeDone = appDiagnostics.span("bgm_decode", {track:name});
      try {
      decoded =
        await this.ctx.decodeAudioData(
          arrayBuffer.slice(0)
        );

      decodeDone();
      } catch(error) {decodeDone("error");throw error;}
      } catch(error) {downloadDone("error");throw error;}
      this.buffers.set(name, decoded);
      return decoded;
    }

    async play(name, force = false) {
      if (!name) {
        return false;
      }

      this.ensureContext();

      if (
        !force &&
        this.currentName === name &&
        this.currentSource
      ) {
        await this.ensureRunning();
        return true;
      }

      const generation =
        ++this.playGeneration;

      let buffer;

      try {
        buffer =
          await this.loadBuffer(name);
      } catch (error) {
        console.error(
          "BGM load error",
          error
        );
        return false;
      }

      if (
        generation !==
        this.playGeneration
      ) {
        return false;
      }

      const ready =
        await this.ensureRunning();

      if (!ready) {
        return false;
      }

      const newSource =
        this.ctx.createBufferSource();

      const newSourceGain =
        this.ctx.createGain();

      newSource.buffer = buffer;
      newSource.loop = true;

      newSourceGain.gain.value = 0.0001;

      newSource.connect(newSourceGain);
      newSourceGain.connect(
        this.masterGain
      );

      const oldSource =
        this.currentSource;

      const oldSourceGain =
        this.currentSourceGain;

      const now = this.ctx.currentTime;

      newSource.start(0);

      newSourceGain.gain.setValueAtTime(
        0.0001,
        now
      );

      newSourceGain.gain.linearRampToValueAtTime(
        1.0,
        now + 0.18
      );

      this.currentName = name;
      this.currentSource = newSource;
      this.currentSourceGain =
        newSourceGain;

      if (
        oldSource &&
        oldSourceGain
      ) {
        try {
          oldSourceGain.gain
            .cancelScheduledValues(now);

          oldSourceGain.gain
            .setValueAtTime(
              Math.max(
                0.0001,
                oldSourceGain.gain.value
              ),
              now
            );

          oldSourceGain.gain
            .linearRampToValueAtTime(
              0.0001,
              now + 0.18
            );

          setTimeout(() => {
            try {
              oldSource.stop();
            } catch (error) {}
            try {
              oldSource.disconnect();
            } catch (error) {}
            try {
              oldSourceGain.disconnect();
            } catch (error) {}
          }, 230);
        } catch (error) {}
      }

      return true;
    }

    async keepAlive() {
      const ready =
        await this.ensureRunning();

      if (!ready) {
        return false;
      }

      // マイク開始時にブラウザがAudioContextを
      // 一時停止しても、ここでは同じ再生ノードを維持する。
      // BGMのpause/startは行わない。
      return true;
    }

    stop() {
      ++this.playGeneration;

      if (this.currentSource) {
        try {
          this.currentSource.stop();
        } catch (error) {}

        try {
          this.currentSource.disconnect();
        } catch (error) {}
      }

      if (this.currentSourceGain) {
        try {
          this.currentSourceGain.disconnect();
        } catch (error) {}
      }

      this.currentSource = null;
      this.currentSourceGain = null;
      this.currentName = null;
    }

    hasActiveSource() {
      return Boolean(
        this.currentSource &&
        this.currentName
      );
    }
  }

  const bgmEngine =
    new BgmEngine(BGM_URLS);

  const randInt = (min, max) =>
    Math.floor(Math.random() * (max - min + 1)) + min;

  // 暗算モードの旧呼び出し名も同じ実装へ統一。
  const randomInt = randInt;

  const coin = () => Math.random() < 0.5;

  function calculate(a, op, b) {
    if (op === "＋") return a + b;
    if (op === "－") return a - b;
    if (op === "×") return a * b;
    return a / b;
  }

  function questionTerms(q) {
    if (
      Array.isArray(q?.terms) &&
      q.terms.length >= 2
    ) {
      return q.terms.map(Number);
    }

    return [
      Number(q?.a),
      Number(q?.b)
    ];
  }

  function questionOperators(q) {
    const terms = questionTerms(q);

    if (
      Array.isArray(q?.operators) &&
      q.operators.length === terms.length - 1
    ) {
      return q.operators.map(String);
    }

    return Array.from(
      { length: Math.max(0, terms.length - 1) },
      () => String(q?.op || "")
    );
  }

  function isMultiTermQuestion(q) {
    return questionTerms(q).length > 2;
  }

  function calculateQuestionSequence(q) {
    const terms = questionTerms(q);
    const operators = questionOperators(q);

    if (
      terms.length < 2 ||
      operators.length !== terms.length - 1 ||
      terms.some((value) => !Number.isFinite(value))
    ) {
      return null;
    }

    let value = terms[0];

    for (let i = 0; i < operators.length; i += 1) {
      value = calculate(
        value,
        operators[i],
        terms[i + 1]
      );

      if (!Number.isFinite(value)) {
        return null;
      }
    }

    return value;
  }

  function questionFormula(q, spaced = true) {
    const terms = questionTerms(q);
    const operators = questionOperators(q);

    if (!terms.length) {
      return "";
    }

    let formula = String(terms[0]);

    for (let i = 0; i < operators.length; i += 1) {
      formula += spaced
        ? ` ${operators[i]} ${terms[i + 1]}`
        : `${operators[i]}${terms[i + 1]}`;
    }

    return formula;
  }

  function isValidQuestion(q) {
    if (!q) return false;

    if (q.op === "＋" || q.op === "－") {
      const terms = questionTerms(q);
      const operators = questionOperators(q);

      if (
        terms.length < 2 ||
        operators.length !== terms.length - 1 ||
        terms.some(
          (value) =>
            !Number.isInteger(value) ||
            value < RULES.addSubOperandMin
        )
      ) {
        return false;
      }

      let running = terms[0];

      for (let i = 0; i < operators.length; i += 1) {
        const op = operators[i];
        const amount = terms[i + 1];

        if (op !== "＋" && op !== "－") {
          return false;
        }

        running = calculate(running, op, amount);

        if (
          op === "－" &&
          running < RULES.subtractionMinAnswer
        ) {
          return false;
        }
      }

      return running === Number(q.answer);
    }

    if (q.op === "÷") {
      if (q.b <= 0) return false;
      if (RULES.divisionMustBeInteger && !Number.isInteger(q.answer)) {
        return false;
      }
    }

    return true;
  }

  function makeQuestion(rawA, op, rawB) {
    // 割り算以外は、計算式確定直前に左右へ必ず+1。
    const a = op === "÷" ? rawA : rawA + 1;
    const b = op === "÷" ? rawB : rawB + 1;

    const q = {
      a,
      op,
      b,
      answer: calculate(a, op, b)
    };

    if (!isValidQuestion(q)) {
      throw new Error(
        `禁止問題: raw=${rawA} ${op} ${rawB}, final=${a} ${op} ${b}`
      );
    }

    return q;
  }

  function makeSequenceQuestion(terms, op) {
    const safeTerms = terms.map(
      (value) => Number(value)
    );

    const operators = Array.from(
      { length: safeTerms.length - 1 },
      () => op
    );

    const q = {
      a: safeTerms[0],
      b: safeTerms[1],
      op,
      terms: safeTerms,
      operators,
      answer: null,
      isWeakness: false,
      weaknessKey: null
    };

    q.answer = calculateQuestionSequence(q);

    if (!isValidQuestion(q)) {
      throw new Error(
        `連続計算問題を生成できません: ${questionFormula(q)}`
      );
    }

    return q;
  }

  function makeAddSub(finalMin, finalMax) {
    const rawMin = Math.max(0, finalMin - 1);
    const rawMax = finalMax - 1;
    const op = coin() ? "＋" : "－";

    if (op === "＋") {
      return makeQuestion(
        randInt(rawMin, rawMax),
        "＋",
        randInt(rawMin, rawMax)
      );
    }

    const rawA = randInt(rawMin, rawMax);
    const rawB = randInt(rawMin, rawA);
    return makeQuestion(rawA, "－", rawB);
  }

  function makeAdditionOnly(finalMin, finalMax) {
    const rawMin = Math.max(0, finalMin - 1);
    const rawMax = finalMax - 1;

    return makeQuestion(
      randInt(rawMin, rawMax),
      "＋",
      randInt(rawMin, rawMax)
    );
  }

  function makeSubtractionOnly(finalMin, finalMax) {
    const rawMin = Math.max(0, finalMin - 1);
    const rawMax = finalMax - 1;

    // rawA >= rawB としておき、最終+1後も大小関係を維持する。
    const rawA = randInt(rawMin, rawMax);
    const rawB = randInt(rawMin, rawA);

    return makeQuestion(rawA, "－", rawB);
  }


  function makeMultiAddition(
    termCount,
    minValue,
    maxValue
  ) {
    const terms = Array.from(
      { length: termCount },
      () => randInt(minValue, maxValue)
    );

    return makeSequenceQuestion(
      terms,
      "＋"
    );
  }

  function makeMultiSubtraction(
    termCount,
    firstMin,
    firstMax,
    subtractMin,
    subtractMax
  ) {
    const subtractCount = termCount - 1;
    const minimumRequired =
      subtractMin * subtractCount;

    for (let tries = 0; tries < 2000; tries += 1) {
      const first = randInt(
        Math.max(firstMin, minimumRequired),
        firstMax
      );

      let remaining = first;
      const subtractors = [];
      let valid = true;

      for (let i = 0; i < subtractCount; i += 1) {
        const remainingSlots = subtractCount - i - 1;
        const maxAllowed = Math.min(
          subtractMax,
          remaining - subtractMin * remainingSlots
        );

        if (maxAllowed < subtractMin) {
          valid = false;
          break;
        }

        const amount = randInt(
          subtractMin,
          maxAllowed
        );

        subtractors.push(amount);
        remaining -= amount;
      }

      if (!valid) {
        continue;
      }

      return makeSequenceQuestion(
        [first, ...subtractors],
        "－"
      );
    }

    throw new Error(
      `連続引き算を生成できません: count=${termCount}`
    );
  }

  function onesAdditionCarries(a, b) {
    return (
      (Math.abs(a) % 10) +
      (Math.abs(b) % 10)
    ) >= 10;
  }

  function onesSubtractionBorrows(a, b) {
    return (
      Math.abs(a) % 10
    ) < (
      Math.abs(b) % 10
    );
  }

  function makeAdditionByOnesCarry(
    digitLevel,
    carryRequired
  ) {
    for (
      let tries = 0;
      tries < 2000;
      tries += 1
    ) {
      const min =
        digitLevel === 1
          ? 1
          : 10;

      const max =
        digitLevel === 1
          ? 9
          : 99;

      const a = randInt(min, max);
      const b = randInt(min, max);

      if (
        digitLevel === 2 &&
        a + b > 99
      ) {
        continue;
      }

      if (
        onesAdditionCarries(a, b) !==
        Boolean(carryRequired)
      ) {
        continue;
      }

      // 非除算は従来どおり raw 値から +1 して確定する。
      return makeQuestion(
        a - 1,
        "＋",
        b - 1
      );
    }

    throw new Error(
      `繰り上がり条件の足し算を生成できません: level=${digitLevel}, carry=${carryRequired}`
    );
  }

  function makeSubtractionByOnesBorrow(
    digitLevel,
    borrowRequired
  ) {
    for (
      let tries = 0;
      tries < 2000;
      tries += 1
    ) {
      let a;
      let b;

      if (
        digitLevel === 1 &&
        borrowRequired
      ) {
        // 例: 12-7。引く数は1桁のまま、十の位から必ず繰り下がる。
        a = randInt(10, 18);
        b = randInt(1, 9);
      } else if (
        digitLevel === 1
      ) {
        a = randInt(1, 9);
        b = randInt(1, a);
      } else {
        a = randInt(10, 99);
        b = randInt(10, a);
      }

      if (a < b) {
        continue;
      }

      if (
        onesSubtractionBorrows(a, b) !==
        Boolean(borrowRequired)
      ) {
        continue;
      }

      return makeQuestion(
        a - 1,
        "－",
        b - 1
      );
    }

    throw new Error(
      `繰り下がり条件の引き算を生成できません: level=${digitLevel}, borrow=${borrowRequired}`
    );
  }

  function questionMatchesMode(
    mode,
    q,
    allowLegacy = false
  ) {
    if (!q) {
      return false;
    }

    const terms = questionTerms(q);
    const a = terms[0];
    const b = terms[1];

    const calculatedAnswer =
      calculateQuestionSequence(q);

    if (
      terms.some((value) => !Number.isFinite(value)) ||
      !Number.isFinite(calculatedAnswer)
    ) {
      return false;
    }

    const answer =
      Number.isFinite(Number(q.answer))
        ? Number(q.answer)
        : calculatedAnswer;

    const allInRange = (min, max) =>
      terms.every(
        (value) =>
          value >= min && value <= max
      );

    if (mode === "ba1") {
      return q.op === "＋" && terms.length === 2 && allInRange(1, 9) && !onesAdditionCarries(a, b);
    }

    if (mode === "ba2") {
      return q.op === "＋" && terms.length === 2 && allInRange(1, 9) && onesAdditionCarries(a, b);
    }

    if (mode === "ba2x4") {
      return q.op === "＋" && terms.length === 4 && allInRange(1, 9);
    }

    if (mode === "ba3") {
      return q.op === "＋" && terms.length === 2 && allInRange(10, 99) && a + b <= 99 && !onesAdditionCarries(a, b);
    }

    if (mode === "ba4") {
      return q.op === "＋" && terms.length === 2 && allInRange(10, 99) && a + b <= 99 && onesAdditionCarries(a, b);
    }

    if (mode === "ba4x4") {
      return q.op === "＋" && terms.length === 4 && allInRange(10, 99);
    }

    if (mode === "ba5") {
      return q.op === "＋" && terms.length === 2 && allInRange(100, 999);
    }

    if (mode === "ba5x4") {
      return q.op === "＋" && terms.length === 4 && allInRange(100, 999);
    }

    if (mode === "bs1") {
      return q.op === "－" && terms.length === 2 && allInRange(1, 9) && a >= b && !onesSubtractionBorrows(a, b);
    }

    if (mode === "bs2") {
      return q.op === "－" && terms.length === 2 && a >= 10 && a <= 18 && b >= 1 && b <= 9 && a >= b && onesSubtractionBorrows(a, b);
    }

    if (mode === "bs2x4") {
      const currentShape = a >= 10 && a <= 99 && terms.slice(1).every((value) => value >= 1 && value <= 9);
      // Keep earned rank certification from the former curriculum; do not reissue its questions.
      return q.op === "－" && terms.length === 4 && answer >= 0 &&
        (currentShape || (allowLegacy && allInRange(1, 9)));
    }

    if (mode === "bs3") {
      return q.op === "－" && terms.length === 2 && allInRange(10, 99) && a >= b && !onesSubtractionBorrows(a, b);
    }

    if (mode === "bs4") {
      return q.op === "－" && terms.length === 2 && allInRange(10, 99) && a >= b && onesSubtractionBorrows(a, b);
    }

    if (mode === "bs4x4") {
      return q.op === "－" && terms.length === 4 && allInRange(10, 99) && answer >= 0;
    }

    if (mode === "bs5") {
      return q.op === "－" && terms.length === 2 && allInRange(100, 999) && a >= b;
    }

    if (mode === "bs5x4") {
      return q.op === "－" && terms.length === 5 && a >= 500 && a <= 999 && terms.slice(1).every((value) => value >= 10 && value <= 99) && answer >= 0;
    }

    return true;
  }

  function makeMul(finalAMin, finalAMax, finalBMin, finalBMax) {
    const rawAMin = Math.max(0, finalAMin - 1);
    const rawAMax = finalAMax - 1;
    const rawBMin = Math.max(0, finalBMin - 1);
    const rawBMax = finalBMax - 1;

    return makeQuestion(
      randInt(rawAMin, rawAMax),
      "×",
      randInt(rawBMin, rawBMax)
    );
  }

  function makeExactDivision(numeratorMin, numeratorMax, divisorMin, divisorMax) {
    const divisorStart = Math.max(1, divisorMin);

    for (let tries = 0; tries < 1000; tries += 1) {
      const divisor = randInt(divisorStart, divisorMax);
      const quotientMin = Math.max(1, Math.ceil(numeratorMin / divisor));
      const quotientMax = Math.floor(numeratorMax / divisor);

      if (quotientMin <= quotientMax) {
        const quotient = randInt(quotientMin, quotientMax);
        return makeQuestion(divisor * quotient, "÷", divisor);
      }
    }

    throw new Error("整数になる割り算を生成できませんでした。");
  }

  function loadChallengeCounts() {
    try {
      const raw =
        localStorage.getItem(
          CHALLENGE_COUNT_STORAGE_KEY
        );

      if (!raw) {
        return {};
      }

      const parsed =
        JSON.parse(raw);

      if (
        !parsed ||
        typeof parsed !== "object" ||
        Array.isArray(parsed)
      ) {
        return {};
      }

      return parsed;
    } catch (error) {
      return {};
    }
  }

  function saveChallengeCounts() {
    try {
      localStorage.setItem(
        CHALLENGE_COUNT_STORAGE_KEY,
        JSON.stringify(
          challengeCounts
        )
      );
    } catch (error) {
      // 保存できなくてもゲーム自体は継続する。
    }
  }

  function getChallengeCount(mode) {
    return Math.max(
      0,
      Math.floor(
        Number(
          challengeCounts[mode]
        ) || 0
      )
    );
  }

  function incrementChallengeCount(mode) {
    const next =
      getChallengeCount(mode) + 1;

    challengeCounts[mode] = next;
    saveChallengeCounts();

    updateModeChallengeCountLabels();

    return next;
  }

  const KUKU_LEVEL_NAMES = Object.freeze({
    1: "初級",
    2: "中級",
    3: "上級",
    4: "特級",
    5: "名人"
  });

  function kukuLevelName(level) {
    return (
      KUKU_LEVEL_NAMES[
        Number(level)
      ] || "九九"
    );
  }

  function kukuChallengeCountKey(
    level
  ) {
    return `kuku-level-${Math.max(
      1,
      Math.min(
        5,
        Number(level) || 1
      )
    )}`;
  }

  function getKukuChallengeCount(
    level
  ) {
    return getChallengeCount(
      kukuChallengeCountKey(
        level
      )
    );
  }

  function incrementKukuChallengeCount(
    level
  ) {
    return incrementChallengeCount(
      kukuChallengeCountKey(
        level
      )
    );
  }

  function createEmptyKukuMedalEntry() {
    return { gold: 0, silver: 0, bronze: 0 };
  }

  function createEmptyKukuMedalStats() {
    const stats = {};
    for (let level = 1; level <= 5; level += 1) {
      stats[level] = createEmptyKukuMedalEntry();
    }
    return stats;
  }

  function normalizeKukuLevel(level) {
    return Math.max(1, Math.min(5, Number(level) || 1));
  }

  function loadKukuMedalStats() {
    const base = createEmptyKukuMedalStats();
    try {
      const raw = localStorage.getItem(KUKU_MEDAL_STORAGE_KEY);
      if (!raw) return base;
      const parsed = JSON.parse(raw);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return base;
      for (let level = 1; level <= 5; level += 1) {
        const source = parsed[level] || parsed[String(level)] || {};
        for (const def of KUKU_MEDAL_DEFS) {
          base[level][def.key] = Math.max(0, Math.floor(Number(source?.[def.key]) || 0));
        }
      }
      return base;
    } catch (error) {
      return base;
    }
  }

  function saveKukuMedalStats() {
    try {
      localStorage.setItem(KUKU_MEDAL_STORAGE_KEY, JSON.stringify(kukuMedalStats));
    } catch (error) {}
  }

  function ensureKukuMedalEntry(level) {
    const normalized = normalizeKukuLevel(level);
    if (!kukuMedalStats || typeof kukuMedalStats !== "object") {
      kukuMedalStats = createEmptyKukuMedalStats();
    }
    if (!kukuMedalStats[normalized]) {
      kukuMedalStats[normalized] = createEmptyKukuMedalEntry();
    }
    return kukuMedalStats[normalized];
  }

  function getKukuMedalCount(level, tierKey) {
    const entry = ensureKukuMedalEntry(level);
    return Math.max(0, Math.floor(Number(entry?.[tierKey]) || 0));
  }

  function renderKukuMedalSummaries() {
    root.querySelectorAll("[data-kuku-level-card]").forEach((card) => {
      const level = normalizeKukuLevel(card.dataset.kukuLevelCard);
      for (const def of KUKU_MEDAL_DEFS) {
        const node = card.querySelector(`[data-kuku-medal="${def.key}"]`);
        if (node) node.textContent = `×${getKukuMedalCount(level, def.key)}`;
      }
    });
  }

  function awardKukuMedal(level, correct, total) {
    const safeTotal = Math.max(1, Number(total) || 0);
    const accuracy = Math.max(0, Number(correct) || 0) / safeTotal;
    const tier = accuracy >= 0.95 ? "gold" : accuracy >= 0.90 ? "silver" : accuracy >= 0.80 ? "bronze" : null;
    if (!tier) return null;
    const entry = ensureKukuMedalEntry(level);
    entry[tier] = getKukuMedalCount(level, tier) + 1;
    saveKukuMedalStats();
    renderKukuMedalSummaries();
    return tier;
  }

  function kukuMedalLabel(tierKey) {
    return KUKU_MEDAL_DEFS.find((def) => def.key === tierKey)?.label || "";
  }

  function loadChallengeMedalStats() {
    const modes = {};
    for (const mode of Object.keys(modeInfo)) modes[mode] = createEmptyKukuMedalEntry();
    try {
      const parsed = JSON.parse(localStorage.getItem(CHALLENGE_MEDAL_STORAGE_KEY) || "{}");
      const source = parsed?.modes;
      if (source && typeof source === "object" && !Array.isArray(source)) {
        for (const mode of Object.keys(modes)) {
          for (const tier of ["gold", "silver", "bronze"]) {
            const count = Number(source[mode]?.[tier]);
            if (Number.isSafeInteger(count) && count >= 0) modes[mode][tier] = count;
          }
        }
      }
    } catch (error) {}
    return { version: 1, modes };
  }

  function challengeMedalCount(mode, tier) {
    return challengeMedalStats.modes[mode]?.[tier] || 0;
  }

  function renderChallengeMedalSummaries() {
    root.querySelectorAll("[data-challenge-medal-mode]").forEach((strip) => {
      const mode = strip.dataset.challengeMedalMode;
      strip.querySelectorAll("[data-challenge-medal]").forEach((node) => {
        const tier = node.dataset.challengeMedal;
        const count = challengeMedalCount(mode, tier);
        node.textContent = `×${count}`;
        node.setAttribute("aria-label", `${getMedalTierDefinition(tier).label}メダル ${count}枚`);
      });
    });
  }

  function setupChallengeMedalSummaries() {
    const images = root.querySelector("#homeAddSubMedal")?.dataset;
    root.querySelectorAll(".start-mode").forEach((button) => {
      const card = button.closest(".mode-card");
      const mode = button.dataset.mode;
      if (!card || !modeInfo[mode] || card.querySelector("[data-challenge-medal-mode]")) return;
      const head = document.createElement("div");
      head.className = "challenge-medal-head";
      const label = card.querySelector(".mode-no");
      if (label) { card.insertBefore(head, label); head.appendChild(label); }
      else card.prepend(head);
      const strip = document.createElement("div");
      strip.className = "kuku-medal-strip challenge-medal-strip";
      strip.dataset.challengeMedalMode = mode;
      strip.setAttribute("role", "group");
      strip.setAttribute("aria-label", "このモードのメダル獲得数");
      for (const tier of ["gold", "silver", "bronze"]) {
        const def = getMedalTierDefinition(tier);
        const chip = document.createElement("span");
        chip.className = `kuku-medal-chip ${tier}`;
        chip.title = `${def.label}：${def.minCorrect}/12以上${def.timedOnly ? "・5分以内" : ""}`;
        const image = document.createElement("img");
        image.className = "kuku-medal-image";
        image.src = images?.[`${tier}Src`] || "";
        image.alt = `${def.label}メダル`;
        const count = document.createElement("span");
        count.className = "count";
        count.dataset.challengeMedal = tier;
        chip.appendChild(image);
        chip.appendChild(count);
        strip.appendChild(chip);
      }
      head.appendChild(strip);
    });
    renderChallengeMedalSummaries();
  }

  function awardChallengeMedal(scoreInfo, timeup) {
    if (sessionChallengeMedalAwarded || !modeInfo[currentMode] ||
        activeRemedialSkillId || activeWeaknessChallengeMode ||
        sessionTotalQuestions !== TOTAL_QUESTIONS || answers.length !== TOTAL_QUESTIONS) {
      return sessionChallengeMedalTier;
    }
    // 既存の認定基準を使用し、1回のチャレンジでは最高の1色だけ加算する。
    sessionChallengeMedalAwarded = true;
    const correct = Number(scoreInfo?.correctCount);
    const tier = [...MEDAL_TIERS].reverse().find((def) =>
      Number.isInteger(correct) && correct >= def.minCorrect && correct <= TOTAL_QUESTIONS &&
      (!def.timedOnly || !timeup)
    );
    sessionChallengeMedalTier = tier?.key || null;
    if (!tier) return null;
    challengeMedalStats.modes[currentMode][tier.key] += 1;
    try {
      localStorage.setItem(CHALLENGE_MEDAL_STORAGE_KEY, JSON.stringify(challengeMedalStats));
    } catch (error) {}
    renderChallengeMedalSummaries();
    return tier.key;
  }

  function randomKukuEncouragement() {
    // 約3回に1回だけ、固定ではない応援コメントを加える。
    if (Math.random() >= 1 / 3) {
      return "";
    }

    const messages = [
      "くり返し挑戦できていますね。",
      "少しずつ力を積み重ねていますね。",
      "今日もよく取り組みました。",
      "続ける力がついていますね。",
      "この調子で練習を重ねていきましょう。",
      "九九をすばやく答える練習ができていますね。"
    ];

    return messages[
      Math.floor(
        Math.random() *
        messages.length
      )
    ];
  }

  function speakKukuFinishSummary({
    level,
    challengeCount,
    perfect = false
  }) {
    if (
      !("speechSynthesis" in window) ||
      typeof SpeechSynthesisUtterance ===
        "undefined"
    ) {
      return;
    }

    const levelName =
      kukuLevelName(level);

    const encouragement =
      randomKukuEncouragement();

    const messages = [];

    if (perfect) {
      messages.push(
        "お見事！パーフェクト！"
      );
    }

    messages.push(
      `${levelName}は、今回で${challengeCount}回目のチャレンジでした。`
    );

    if (encouragement) {
      messages.push(
        encouragement
      );
    }

    try {
      cancelAppSpeech();
    } catch (error) {}

    waitForJapaneseVoice(1000)
      .then((voice) => {
        let messageIndex = 0;

        const speakNext = () => {
          if (
            messageIndex >=
            messages.length
          ) {
            return;
          }

          const utterance =
            new SpeechSynthesisUtterance(
              messages[messageIndex]
            );

          utterance.lang = "ja-JP";
          utterance.rate = 0.96;
          utterance.pitch = 1.03;
          utterance.volume = appMasterVolume;

          if (voice) {
            utterance.voice = voice;
          }

          utterance.onend = () => {
            messageIndex += 1;

            setTimeout(
              speakNext,
              120
            );
          };

          utterance.onerror =
            utterance.onend;

          speakWithAppVolume(
            utterance
          );
        };

        speakNext();
      })
      .catch(() => {
        try {
          const utterance =
            new SpeechSynthesisUtterance(
              messages.join(" ")
            );

          utterance.lang = "ja-JP";
          utterance.rate = 0.96;
          utterance.pitch = 1.03;
          utterance.volume = appMasterVolume;

          speakWithAppVolume(
            utterance
          );
        } catch (error) {}
      });
  }

  function modeVoiceName(mode) {
    const title =
      modeInfo[mode]?.title ||
      mode;

    return String(title)
      .split("｜")[0];
  }

  function updateModeChallengeCountLabels() {
    root
      .querySelectorAll(
        ".mode-challenge-count"
      )
      .forEach((node) => {
        const mode =
          node.dataset.mode;

        if (!mode) {
          return;
        }

        node.textContent =
          `総チャレンジ ${getChallengeCount(mode)}回`;
      });
  }

  function setupModeChallengeCountLabels() {
    root
      .querySelectorAll(
        ".start-mode"
      )
      .forEach((startButton) => {
        const mode =
          startButton.dataset.mode;

        if (!mode) {
          return;
        }

        const card =
          startButton.closest(
            ".mode-card"
          );

        if (!card) {
          return;
        }

        if (
          card.querySelector(
            `.mode-challenge-count[data-mode="${mode}"]`
          )
        ) {
          return;
        }

        const label =
          document.createElement(
            "div"
          );

        label.className =
          "mode-challenge-count";

        label.dataset.mode =
          mode;

        startButton.insertAdjacentElement(
          "beforebegin",
          label
        );
      });

    updateModeChallengeCountLabels();
  }

  function loadScoreRankings() {
    try {
      const raw =
        localStorage.getItem(
          RANKING_STORAGE_KEY
        );

      if (!raw) {
        return { modes: {} };
      }

      const parsed =
        JSON.parse(raw);

      if (
        !parsed ||
        typeof parsed !== "object"
      ) {
        return { modes: {} };
      }

      if (
        !parsed.modes ||
        typeof parsed.modes !== "object"
      ) {
        parsed.modes = {};
      }

      return parsed;
    } catch (error) {
      return { modes: {} };
    }
  }

  function saveScoreRankings() {
    try {
      localStorage.setItem(
        RANKING_STORAGE_KEY,
        JSON.stringify(
          scoreRankings
        )
      );
    } catch (error) {
      // 保存できなくてもゲーム自体は継続する。
    }
  }

  function rankingEntriesForMode(mode) {
    const entries =
      scoreRankings.modes[mode];

    if (!Array.isArray(entries)) {
      return [];
    }

    return [...entries].sort(
      (a, b) =>
        (b.score - a.score) ||
        (b.correctCount - a.correctCount) ||
        (b.maxStreak - a.maxStreak) ||
        (b.remainingSeconds - a.remainingSeconds) ||
        (a.playedAt - b.playedAt)
    );
  }

  function addScoreRanking(
    mode,
    scoreInfo,
    timeup
  ) {
    if (!mode || !scoreInfo) {
      return;
    }

    if (
      !scoreRankings.modes[mode] ||
      !Array.isArray(
        scoreRankings.modes[mode]
      )
    ) {
      scoreRankings.modes[mode] = [];
    }

    const entry = {
      id:
        `${Date.now()}-` +
        Math.random()
          .toString(36)
          .slice(2, 9),
      score:
        Number(scoreInfo.finalScore) || 0,
      correctCount:
        Number(scoreInfo.correctCount) || 0,
      maxStreak:
        Number(scoreInfo.maxStreak) || 0,
      remainingSeconds:
        Number(scoreInfo.remainingSeconds) || 0,
      wrongCount:
        Number(scoreInfo.wrongCount) || 0,
      hintCount:
        Number(scoreInfo.hintCount) || 0,
      timeup:
        Boolean(timeup),
      playedAt:
        Date.now()
    };

    scoreRankings.modes[mode].push(
      entry
    );

    scoreRankings.modes[mode] =
      rankingEntriesForMode(mode)
        .slice(
          0,
          MAX_RANKING_ENTRIES_PER_MODE
        );

    saveScoreRankings();
  }

  function deleteRankingEntry(
    mode,
    entryId
  ) {
    const entries =
      scoreRankings.modes[mode];

    if (!Array.isArray(entries)) {
      return;
    }

    scoreRankings.modes[mode] =
      entries.filter(
        (entry) =>
          entry.id !== entryId
      );

    saveScoreRankings();

    if (currentMode === mode) {
      renderResultRanking(mode);
    }

    if (rankingModalMode === mode) {
      renderRankingList(
        rankingModalList,
        mode
      );
    }
  }

  function formatRankingTime(
    secondsValue
  ) {
    const safe =
      Math.max(
        0,
        Math.floor(
          Number(secondsValue) || 0
        )
      );

    const minutes =
      Math.floor(safe / 60);

    const secondsPart =
      safe % 60;

    return (
      `${minutes}:` +
      String(secondsPart)
        .padStart(2, "0")
    );
  }

  function formatRankingDate(
    timestamp
  ) {
    try {
      return new Date(timestamp)
        .toLocaleString(
          "ja-JP",
          {
            month: "numeric",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit"
          }
        );
    } catch (error) {
      return "";
    }
  }

  function renderRankingList(
    container,
    mode
  ) {
    if (!container) {
      return;
    }

    container.innerHTML = "";

    const entries =
      rankingEntriesForMode(mode);

    if (entries.length === 0) {
      const empty =
        document.createElement(
          "div"
        );

      empty.className =
        "ranking-empty";

      empty.textContent =
        "まだ得点記録がありません。";

      container.appendChild(empty);
      return;
    }

    entries.forEach(
      (entry, index) => {
        const row =
          document.createElement(
            "div"
          );

        row.className =
          "ranking-row";

        const place =
          document.createElement(
            "div"
          );

        place.className =
          "ranking-place";

        place.textContent =
          `${index + 1}`;

        const main =
          document.createElement(
            "div"
          );

        main.className =
          "ranking-main";

        const scoreEl =
          document.createElement(
            "div"
          );

        scoreEl.className =
          "ranking-score";

        scoreEl.textContent =
          `${entry.score.toLocaleString()}点`;

        const detail =
          document.createElement(
            "div"
          );

        detail.className =
          "ranking-detail";

        detail.textContent =
          `${entry.correctCount}/${TOTAL_QUESTIONS}正解` +
          ` ・ 最高${entry.maxStreak}連続` +
          ` ・ 残り${formatRankingTime(entry.remainingSeconds)}` +
          ` ・ ${formatRankingDate(entry.playedAt)}`;

        const deleteBtn =
          document.createElement(
            "button"
          );

        deleteBtn.type =
          "button";

        deleteBtn.className =
          "ranking-delete";

        deleteBtn.textContent =
          "削除";

        deleteBtn.addEventListener(
          "click",
          () => {
            const ok =
              window.confirm(
                "この得点記録を削除しますか？"
              );

            if (!ok) {
              return;
            }

            deleteRankingEntry(
              mode,
              entry.id
            );
          }
        );

        main.appendChild(scoreEl);
        main.appendChild(detail);

        row.appendChild(place);
        row.appendChild(main);
        row.appendChild(deleteBtn);

        container.appendChild(row);
      }
    );
  }

  function renderResultRanking(mode) {
    renderRankingList(
      resultRankingList,
      mode
    );
  }

  function openRankingModal(mode) {
    rankingModalMode = mode;

    rankingModalTitle.textContent =
      `${modeInfo[mode].title}｜得点ランキング`;

    renderRankingList(
      rankingModalList,
      mode
    );

    rankingModal.classList.add(
      "show"
    );

    rankingModal.setAttribute(
      "aria-hidden",
      "false"
    );
  }

  function closeRankingModal() {
    rankingModalMode = null;

    rankingModal.classList.remove(
      "show"
    );

    rankingModal.setAttribute(
      "aria-hidden",
      "true"
    );
  }

  function setupModeRankingButtons() {
    root
      .querySelectorAll(
        ".start-mode"
      )
      .forEach((startButton) => {
        const mode =
          startButton.dataset.mode;

        if (!mode) {
          return;
        }

        const button =
          document.createElement(
            "button"
          );

        button.type =
          "button";

        button.className =
          "ranking-open-btn";

        button.dataset.mode =
          mode;

        button.textContent =
          "過去の得点ランキング（5分）";

        button.addEventListener(
          "click",
          () => {
            openRankingModal(mode);
          }
        );

        startButton.insertAdjacentElement(
          "afterend",
          button
        );
      });
  }

  const SKILL_DEFS = Object.freeze({
    add_direct: {
      title: "足し算の基本操作",
      shortIssue: "足せる珠をそのまま動かす",
      explanation: "同じ位に使える一珠があるときは、その珠をそのまま梁へ寄せます。まずは1〜4の珠の形を見て判断します。",
      category: "add",
      lessonIndex: 0,
      baseMode: "ba1",
      weight: 1.0
    },
    add_five: {
      title: "5の補数",
      shortIssue: "5の補数をすぐ出す",
      explanation: "5をまたぐ足し算では、足したい数をそのまま足せないときに5の補数を使います。たとえば＋4は、先に−1してから＋5です。",
      category: "add",
      lessonIndex: 2,
      baseMode: "ba1",
      weight: 1.2
    },
    add_ten: {
      title: "10の補数・繰り上がり",
      shortIssue: "10の補数をすぐ出す",
      explanation: "10をまたぐ足し算では、先に一の位から10の補数を引き、そのあと1つ上の位へ1を足します。8＋7なら−3→＋10です。",
      category: "add",
      lessonIndex: 3,
      baseMode: "ba2",
      weight: 1.5
    },
    add_multi: {
      title: "複数桁の足し算",
      shortIssue: "位ごとに分けて足す",
      explanation: "2桁以上は大きい位から順に分けます。十の位を処理してから一の位を処理すると、繰り上がりの場所が分かりやすくなります。",
      category: "add",
      lessonIndex: 4,
      baseMode: "ba3",
      weight: 1.7
    },
    sub_direct: {
      title: "引き算の基本操作",
      shortIssue: "取れる珠をそのまま取る",
      explanation: "引きたい数だけ珠があるときは、その珠を梁から離します。答えを新しく作るのではなく、今ある珠から取ります。",
      category: "sub",
      lessonIndex: 0,
      baseMode: "bs1",
      weight: 1.0
    },
    sub_five: {
      title: "5の補数で引く",
      shortIssue: "5の補数で引く",
      explanation: "一珠だけでは引けないときは、先に−5して補数を足し戻します。7−4なら−5→＋1です。",
      category: "sub",
      lessonIndex: 2,
      baseMode: "bs1",
      weight: 1.2
    },
    sub_ten: {
      title: "10の補数・繰り下がり",
      shortIssue: "繰り下がりを安定させる",
      explanation: "一の位だけで引けないときは、先に1つ上の位から1を引き、そのあと10の補数を一の位へ足し戻します。",
      category: "sub",
      lessonIndex: 3,
      baseMode: "bs2",
      weight: 1.5
    },
    sub_multi: {
      title: "複数桁の引き算",
      shortIssue: "位ごとに分けて引く",
      explanation: "2桁以上は大きい位から順に引きます。下の位で足りないときだけ、繰り下がりを使います。",
      category: "sub",
      lessonIndex: 4,
      baseMode: "bs3",
      weight: 1.7
    },
    mul_basic: {
      title: "九九",
      shortIssue: "九九を安定させる",
      explanation: "まず掛け算の答えを確実に出し、そのあと答えを十の位・一の位へ分けて珠に置きます。",
      category: "mul",
      lessonIndex: 0,
      baseMode: "mm1",
      weight: 1.7
    },
    mul_place: {
      title: "掛け算の位取り",
      shortIssue: "部分積の位をそろえる",
      explanation: "2桁以上の掛け算では、十の位と一の位の部分積を分け、元の数字の位を保って足し合わせます。",
      category: "mul",
      lessonIndex: 1,
      baseMode: "mm2",
      weight: 2.1
    },
    div_basic: {
      title: "割り算の基本",
      shortIssue: "割り算の答えを安定させる",
      explanation: "割り算は、割る数を何倍すると元の数になるかを考えます。まず小さい整数の割り算を安定させます。",
      category: "div",
      lessonIndex: 0,
      baseMode: "md1",
      weight: 1.8
    },
    div_place: {
      title: "割り算の位取り",
      shortIssue: "大きい数の割り算を位で考える",
      explanation: "大きい数の割り算では、上の位から商を考え、答えを正しい位へ置きます。",
      category: "div",
      lessonIndex: 1,
      baseMode: "md2",
      weight: 2.2
    }
  });

  function loadSessionHistory() {
    try {
      const raw = localStorage.getItem(
        SESSION_HISTORY_STORAGE_KEY
      );

      if (!raw) {
        return [];
      }

      const parsed = JSON.parse(raw);
      return Array.isArray(parsed)
        ? parsed.slice(-MAX_SESSION_HISTORY)
        : [];
    } catch (error) {
      return [];
    }
  }

  function saveSessionHistory() {
    try {
      sessionHistory = sessionHistory
        .slice(-MAX_SESSION_HISTORY);

      localStorage.setItem(
        SESSION_HISTORY_STORAGE_KEY,
        JSON.stringify(sessionHistory)
      );
    } catch (error) {}
  }

  function digitLength(value) {
    return String(
      Math.abs(
        Math.floor(Number(value) || 0)
      )
    ).length;
  }

  function hasAdditionCarry(a, b) {
    let x = Math.floor(Math.abs(a));
    let y = Math.floor(Math.abs(b));
    let carry = 0;

    while (x > 0 || y > 0 || carry > 0) {
      const dx = x % 10;
      const dy = y % 10;
      const sum = dx + dy + carry;

      if (sum >= 10) {
        return true;
      }

      carry = sum >= 10 ? 1 : 0;
      x = Math.floor(x / 10);
      y = Math.floor(y / 10);
    }

    return false;
  }

  function hasSubtractionBorrow(a, b) {
    let x = Math.floor(Math.abs(a));
    let y = Math.floor(Math.abs(b));
    let borrow = 0;

    while (x > 0 || y > 0) {
      let dx = (x % 10) - borrow;
      const dy = y % 10;

      if (dx < dy) {
        return true;
      }

      borrow = dx < dy ? 1 : 0;
      x = Math.floor(x / 10);
      y = Math.floor(y / 10);
    }

    return false;
  }

  function skillForQuestion(q) {
    if (!q) {
      return "add_direct";
    }

    if (isMultiTermQuestion(q)) {
      return q.op === "－"
        ? "sub_multi"
        : "add_multi";
    }

    if (q.op === "＋") {
      if (
        digitLength(q.a) > 1 ||
        digitLength(q.b) > 1
      ) {
        return "add_multi";
      }

      if (q.a + q.b >= 10) {
        return "add_ten";
      }

      if (
        q.a < 5 &&
        q.b < 5 &&
        q.a + q.b >= 5
      ) {
        return "add_five";
      }

      return "add_direct";
    }

    if (q.op === "－") {
      if (
        digitLength(q.a) === 2 &&
        digitLength(q.b) === 1 &&
        onesSubtractionBorrows(q.a, q.b)
      ) {
        return "sub_ten";
      }

      if (
        digitLength(q.a) > 1 ||
        digitLength(q.b) > 1
      ) {
        return hasSubtractionBorrow(
          q.a,
          q.b
        )
          ? "sub_multi"
          : "sub_direct";
      }

      if (
        q.a >= 5 &&
        q.b < 5 &&
        (q.a % 5) < q.b
      ) {
        return "sub_five";
      }

      return "sub_direct";
    }

    if (q.op === "×") {
      return (
        q.a <= 9 &&
        q.b <= 9
      )
        ? "mul_basic"
        : "mul_place";
    }

    if (q.op === "÷") {
      return (
        q.a <= 81 &&
        q.b <= 9
      )
        ? "div_basic"
        : "div_place";
    }

    return "add_direct";
  }

  function collectSkillEvidence() {
    const evidence = {};

    Object.keys(SKILL_DEFS).forEach(
      (skillId) => {
        evidence[skillId] = {
          attempts: 0,
          correct: 0,
          hints: 0
        };
      }
    );

    Object.values(
      learningStats.problems || {}
    ).forEach((stat) => {
      const skillId =
        skillForQuestion(stat);

      if (!evidence[skillId]) {
        return;
      }

      evidence[skillId].attempts +=
        Number(stat.attempts) || 0;

      evidence[skillId].correct +=
        Number(stat.correct) || 0;
    });

    sessionHistory.forEach((session) => {
      (session.questions || [])
        .forEach((question) => {
          const skillId =
            question.skillId ||
            skillForQuestion(question);

          if (
            evidence[skillId] &&
            question.hintUsed
          ) {
            evidence[skillId].hints += 1;
          }
        });
    });

    return evidence;
  }

  function buildRankTrack(
    key,
    label,
    shortLabel,
    definitions
  ) {
    const previousModes = [];

    const ranks = definitions.map(
      (definition, index) => {
        const stageModes = [
          ...definition.stageModes
        ];

        const rule = Object.freeze({
          id: `${key}:${definition.code}`,
          trackKey: key,
          trackLabel: label,
          trackShortLabel: shortLabel,
          index,
          name: definition.name,
          stageModes: Object.freeze(stageModes),
          priorModes: Object.freeze([
            ...previousModes
          ]),
          requirement: definition.requirement
        });

        previousModes.push(
          ...stageModes
        );

        return rule;
      }
    );

    return Object.freeze({
      key,
      label,
      shortLabel,
      ranks: Object.freeze(ranks)
    });
  }

  const RANK_TRACKS = Object.freeze({
    addsub: buildRankTrack(
      "addsub",
      "足し算・引き算",
      "足・引",
      [
        {
          code: "8kyu",
          name: "8級",
          stageModes: ["ba1", "bs1"],
          requirement: "1桁・繰り上がり／繰り下がりなし"
        },
        {
          code: "7kyu",
          name: "7級",
          stageModes: ["ba2", "bs2"],
          requirement: "1桁・繰り上がり／繰り下がりあり"
        },
        {
          code: "6kyu",
          name: "6級",
          stageModes: ["ba2x4", "bs2x4"],
          requirement: "1桁の数を4つ使う足し算・引き算"
        },
        {
          code: "5kyu",
          name: "5級",
          stageModes: ["ba3", "bs3"],
          requirement: "2桁・繰り上がり／繰り下がりなし"
        },
        {
          code: "4kyu",
          name: "4級",
          stageModes: ["ba4", "bs4"],
          requirement: "2桁・繰り上がり／繰り下がりあり"
        },
        {
          code: "3kyu",
          name: "3級",
          stageModes: ["ba4x4", "bs4x4"],
          requirement: "2桁の数を4つ使う足し算・引き算"
        },
        {
          code: "2kyu",
          name: "2級",
          stageModes: ["ba5", "bs5"],
          requirement: "3桁の足し算・引き算"
        },
        {
          code: "1kyu",
          name: "1級",
          stageModes: ["ba5x4", "bs5x4"],
          requirement: "3桁の連続足し算・連続引き算"
        },
        {
          code: "shodan",
          name: "名人",
          stageModes: ["a1"],
          requirement: "4桁の足し算・引き算"
        }
      ]
    ),
    muldiv: buildRankTrack(
      "muldiv",
      "掛け算・割り算",
      "掛・割",
      [
        {
          code: "4kyu",
          name: "4級",
          stageModes: ["mm1", "md1"],
          requirement: "1桁レベルの掛け算・割り算"
        },
        {
          code: "3kyu",
          name: "3級",
          stageModes: ["mm2", "md2"],
          requirement: "2桁×1桁・3桁÷1桁"
        },
        {
          code: "2kyu",
          name: "2級",
          stageModes: ["mm3", "md3"],
          requirement: "2桁×2桁・3桁÷2桁"
        },
        {
          code: "1kyu",
          name: "1級",
          stageModes: ["a2"],
          requirement: "3桁×2桁・4桁÷2桁"
        },
        {
          code: "shodan",
          name: "名人",
          stageModes: ["a3"],
          requirement: "3桁×3桁・5桁÷3桁"
        }
      ]
    )
  });

  const ALL_RANK_RULES = Object.freeze([
    ...RANK_TRACKS.addsub.ranks,
    ...RANK_TRACKS.muldiv.ranks
  ]);

  const RANK_RULE_BY_ID = new Map(
    ALL_RANK_RULES.map(
      (rule) => [rule.id, rule]
    )
  );

  const MEDAL_TIERS = Object.freeze([
    {
      key: "bronze",
      label: "銅",
      minCorrect: 10,
      timedOnly: false,
      description: "10/12以上"
    },
    {
      key: "silver",
      label: "銀",
      minCorrect: 11,
      timedOnly: false,
      description: "11/12以上"
    },
    {
      key: "gold",
      label: "金",
      minCorrect: 11,
      timedOnly: true,
      description: "11/12以上・5分以内にクリア"
    }
  ]);

  const MEDAL_TIER_ORDER = Object.freeze({
    bronze: 0,
    silver: 1,
    gold: 2
  });

  const LEGACY_RANK_TRACK_MAP = Object.freeze({
    "10級": [{ trackKey: "addsub", rankIndex: 0 }],
    "9級": [{ trackKey: "addsub", rankIndex: 0 }],
    "8級": [{ trackKey: "addsub", rankIndex: 1 }],
    "7級": [{ trackKey: "addsub", rankIndex: 2 }],
    "6級": [{ trackKey: "addsub", rankIndex: 3 }],
    "5級": [{ trackKey: "addsub", rankIndex: 4 }],
    "4級": [{ trackKey: "addsub", rankIndex: 5 }],
    "3級": [{ trackKey: "addsub", rankIndex: 6 }],
    "2級": [{ trackKey: "addsub", rankIndex: 7 }],
    "1級": [{ trackKey: "muldiv", rankIndex: 0 }],
    "初段": [{ trackKey: "muldiv", rankIndex: 1 }],
    "二段": [{ trackKey: "muldiv", rankIndex: 2 }],
    "三段": [{ trackKey: "addsub", rankIndex: 8 }],
    "名人": [{ trackKey: "muldiv", rankIndex: 4 }]
  });

  function trackForKey(trackKey) {
    return RANK_TRACKS[trackKey] || null;
  }

  function ruleForId(ruleId) {
    return RANK_RULE_BY_ID.get(ruleId) || null;
  }

  function trackKeyForMode(mode) {
    const value = String(mode || "");

    if (
      value.startsWith("ba") ||
      value.startsWith("bs") ||
      value === "a1"
    ) {
      return "addsub";
    }

    if (
      value.startsWith("mm") ||
      value.startsWith("md") ||
      value === "a2" ||
      value === "a3"
    ) {
      return "muldiv";
    }

    return null;
  }

  function emptyLegacyFloorByTrack() {
    return {
      addsub: null,
      muldiv: null
    };
  }

  function normalizeTierKey(tierKey) {
    return Object.prototype.hasOwnProperty.call(
      MEDAL_TIER_ORDER,
      tierKey
    )
      ? tierKey
      : "bronze";
  }

  function tierKeyFromMedalRecord(record) {
    if (!record || typeof record !== "object") {
      return null;
    }

    if (record.gold) return "gold";
    if (record.silver) return "silver";
    if (record.bronze) return "bronze";
    return null;
  }

  function normalizeLegacyFloorByTrack(raw) {
    const normalized = emptyLegacyFloorByTrack();

    if (!raw || typeof raw !== "object") {
      return normalized;
    }

    Object.keys(normalized).forEach(
      (trackKey) => {
        const floor = raw[trackKey];
        const track = trackForKey(trackKey);

        if (
          !floor ||
          !track ||
          !Number.isInteger(Number(floor.rankIndex))
        ) {
          return;
        }

        normalized[trackKey] = {
          rankIndex: Math.max(
            0,
            Math.min(
              track.ranks.length - 1,
              Number(floor.rankIndex)
            )
          ),
          tierKey: normalizeTierKey(floor.tierKey),
          sourceRank:
            typeof floor.sourceRank === "string"
              ? floor.sourceRank
              : "旧認定"
        };
      }
    );

    return normalized;
  }

  function strongerFloor(current, candidate) {
    if (!candidate) return current || null;
    if (!current) return candidate;

    if (candidate.rankIndex !== current.rankIndex) {
      return candidate.rankIndex > current.rankIndex
        ? candidate
        : current;
    }

    return (
      MEDAL_TIER_ORDER[candidate.tierKey] >
      MEDAL_TIER_ORDER[current.tierKey]
    )
      ? candidate
      : current;
  }

  function deriveLegacyFloorByTrack(rawMedals) {
    const floors = emptyLegacyFloorByTrack();

    if (!rawMedals || typeof rawMedals !== "object") {
      return floors;
    }

    Object.entries(rawMedals).forEach(
      ([rankName, record]) => {
        const tierKey = tierKeyFromMedalRecord(record);
        const mappings = LEGACY_RANK_TRACK_MAP[rankName];

        if (!tierKey || !Array.isArray(mappings)) {
          return;
        }

        mappings.forEach((mapping) => {
          const candidate = {
            rankIndex: mapping.rankIndex,
            tierKey,
            sourceRank: rankName
          };

          floors[mapping.trackKey] = strongerFloor(
            floors[mapping.trackKey],
            candidate
          );
        });
      }
    );

    return floors;
  }

  function mergeLegacyFloors(primary, secondary) {
    const result = emptyLegacyFloorByTrack();

    Object.keys(result).forEach((trackKey) => {
      result[trackKey] = strongerFloor(
        primary?.[trackKey] || null,
        secondary?.[trackKey] || null
      );
    });

    return result;
  }

  function emptyRankCertificationState(
    resetAt = null,
    legacyFloorByTrack = null
  ) {
    return {
      bestByMode: {},
      medalAchievedAt: {},
      legacyFloorByTrack:
        legacyFloorByTrack ||
        emptyLegacyFloorByTrack(),
      resetAt,
      curriculumVersion:
        CHALLENGE_CURRICULUM_VERSION
    };
  }

  function normalizeAllMedalRecords(raw) {
    const normalized = {};

    if (!raw || typeof raw !== "object") {
      return normalized;
    }

    Object.entries(raw).forEach(
      ([rankKey, value]) => {
        if (
          value &&
          typeof value === "object" &&
          !Array.isArray(value)
        ) {
          normalized[rankKey] = {
            bronze:
              typeof value.bronze === "string"
                ? value.bronze
                : null,
            silver:
              typeof value.silver === "string"
                ? value.silver
                : null,
            gold:
              typeof value.gold === "string"
                ? value.gold
                : null
          };
        }
      }
    );

    return normalized;
  }

  function normalizeNewMedalRecords(raw) {
    const all = normalizeAllMedalRecords(raw);
    const normalized = {};

    Object.entries(all).forEach(
      ([rankId, value]) => {
        if (RANK_RULE_BY_ID.has(rankId)) {
          normalized[rankId] = value;
        }
      }
    );

    return normalized;
  }

  function loadRankCertificationState() {
    try {
      const raw = localStorage.getItem(
        RANK_CERTIFICATION_STORAGE_KEY
      );

      if (!raw) {
        return emptyRankCertificationState();
      }

      const parsed = JSON.parse(raw);

      if (!parsed || typeof parsed !== "object") {
        return emptyRankCertificationState();
      }

      const resetAt =
        parsed.resetAt &&
        !Number.isNaN(Date.parse(parsed.resetAt))
          ? parsed.resetAt
          : null;

      const allOldMedals = normalizeAllMedalRecords(
        parsed.medalAchievedAt
      );

      const migratedFloors = deriveLegacyFloorByTrack(
        allOldMedals
      );

      const savedFloors = normalizeLegacyFloorByTrack(
        parsed.legacyFloorByTrack
      );

      const legacyFloorByTrack = mergeLegacyFloors(
        savedFloors,
        migratedFloors
      );

      const sameCurriculum =
        parsed.curriculumVersion ===
        CHALLENGE_CURRICULUM_VERSION;

      return {
        bestByMode:
          parsed.bestByMode &&
          typeof parsed.bestByMode === "object"
            ? parsed.bestByMode
            : {},
        medalAchievedAt:
          sameCurriculum
            ? normalizeNewMedalRecords(allOldMedals)
            : {},
        legacyFloorByTrack,
        resetAt,
        curriculumVersion:
          CHALLENGE_CURRICULUM_VERSION
      };
    } catch (error) {
      return emptyRankCertificationState();
    }
  }

  let rankCertificationState =
    loadRankCertificationState();

  function saveRankCertificationState() {
    try {
      localStorage.setItem(
        RANK_CERTIFICATION_STORAGE_KEY,
        JSON.stringify(rankCertificationState)
      );
    } catch (error) {}
  }

  function recordTimestampAfterReset(record) {
    const resetTimestamp =
      rankCertificationState.resetAt
        ? Date.parse(rankCertificationState.resetAt)
        : NaN;

    if (!Number.isFinite(resetTimestamp)) {
      return true;
    }

    const recordTimestamp =
      record?.finishedAt
        ? Date.parse(record.finishedAt)
        : NaN;

    return (
      Number.isFinite(recordTimestamp) &&
      recordTimestamp > resetTimestamp
    );
  }

  function certificationCorrectFromRecord(record) {
    const qs = Array.isArray(record?.questions)
      ? record.questions
      : [];

    if (qs.length) {
      return qs.filter(
        (q) =>
          Boolean(q?.ok) &&
          !Boolean(q?.hintUsed)
      ).length;
    }

    return Math.max(
      0,
      Math.min(
        TOTAL_QUESTIONS,
        Number(record?.correctCount) || 0
      )
    );
  }

  function updateRankCertificationState(record) {
    if (
      !record ||
      !recordTimestampAfterReset(record) ||
      record.remedialSkillId ||
      record.weaknessChallengeMode ||
      !record.mode ||
      Number(record.totalQuestions) !== TOTAL_QUESTIONS
    ) {
      return;
    }

    if (
      Array.isArray(record.questions) &&
      record.questions.length > 0 &&
      !record.questions.every(
        (q) => questionMatchesMode(record.mode, q, true)
      )
    ) {
      return;
    }

    const correct = certificationCorrectFromRecord(record);
    const timedCompleted =
      record.timeLimitEnabled === true &&
      !record.timeup;

    const current = {
      correct: 0,
      timedCorrect: 0,
      achievedAt: null,
      timedAchievedAt: null,
      ...(rankCertificationState.bestByMode[record.mode] || {})
    };

    let changed = false;

    if (correct > Number(current.correct || 0)) {
      current.correct = correct;
      current.achievedAt =
        record.finishedAt ||
        new Date().toISOString();
      changed = true;
    }

    if (
      timedCompleted &&
      correct > Number(current.timedCorrect || 0)
    ) {
      current.timedCorrect = correct;
      current.timedAchievedAt =
        record.finishedAt ||
        new Date().toISOString();
      changed = true;
    }

    if (changed) {
      rankCertificationState.bestByMode[record.mode] = current;
      saveRankCertificationState();
    }
  }

  function rebuildRankCertificationStateFromHistory() {
    (sessionHistory || []).forEach(
      (record) => updateRankCertificationState(record)
    );
  }

  function bestCorrectForMode(
    mode,
    timedOnly = false
  ) {
    const entry =
      rankCertificationState.bestByMode[mode] || {};

    const raw = timedOnly
      ? entry.timedCorrect
      : entry.correct;

    return Math.max(
      0,
      Math.min(
        TOTAL_QUESTIONS,
        Number(raw) || 0
      )
    );
  }

  function getMedalTierDefinition(tierKey) {
    return MEDAL_TIERS.find(
      (tier) => tier.key === tierKey
    ) || MEDAL_TIERS[0];
  }

  function modeMeetsTier(mode, tierKey) {
    const tier = getMedalTierDefinition(tierKey);

    return (
      bestCorrectForMode(mode, tier.timedOnly) >=
      tier.minCorrect
    );
  }

  function certificationRuleSatisfied(
    rule,
    tierKey = "bronze"
  ) {
    if (!rule) return false;

    const priorGold = rule.priorModes.every(
      (mode) => modeMeetsTier(mode, "gold")
    );

    const currentTier = rule.stageModes.every(
      (mode) => modeMeetsTier(mode, tierKey)
    );

    return priorGold && currentTier;
  }

  function goalRequirementRows(rule, tierKey) {
    if (!rule) return [];

    return [
      ...rule.priorModes.map((mode) => ({
        mode,
        tierKey: "gold",
        prerequisite: true
      })),
      ...rule.stageModes.map((mode) => ({
        mode,
        tierKey,
        prerequisite: false
      }))
    ];
  }

  function certificationRuleProgress(
    rule,
    tierKey = "bronze"
  ) {
    const rows = goalRequirementRows(rule, tierKey);

    if (!rows.length) return 0;

    const ratios = rows.map((row) => {
      const tier = getMedalTierDefinition(row.tierKey);

      return Math.max(
        0,
        Math.min(
          1,
          bestCorrectForMode(
            row.mode,
            tier.timedOnly
          ) / tier.minCorrect
        )
      );
    });

    return (
      ratios.reduce((sum, value) => sum + value, 0) /
      ratios.length *
      100
    );
  }

  function shortModeName(mode) {
    const title = modeInfo[mode]?.title || mode;
    const pieces = String(title).split("｜");
    return pieces[pieces.length - 1] || title;
  }

  function certificationEvidenceText(
    rule,
    tierKey = "bronze"
  ) {
    if (!rule) return "";

    return goalRequirementRows(rule, tierKey)
      .map((row) => {
        const tier = getMedalTierDefinition(row.tierKey);
        const score = bestCorrectForMode(
          row.mode,
          tier.timedOnly
        );

        return `${shortModeName(row.mode)} ${score}/12`;
      })
      .join("・");
  }

  function medalRecordForRule(ruleOrId) {
    const ruleId =
      typeof ruleOrId === "string"
        ? ruleOrId
        : ruleOrId?.id;

    const raw =
      rankCertificationState.medalAchievedAt[ruleId];

    if (
      !raw ||
      typeof raw !== "object" ||
      Array.isArray(raw)
    ) {
      return {
        bronze: null,
        silver: null,
        gold: null
      };
    }

    return {
      bronze:
        typeof raw.bronze === "string"
          ? raw.bronze
          : null,
      silver:
        typeof raw.silver === "string"
          ? raw.silver
          : null,
      gold:
        typeof raw.gold === "string"
          ? raw.gold
          : null
    };
  }

  function highestMedalTierForRule(ruleOrId) {
    const record = medalRecordForRule(ruleOrId);

    if (record.gold) return "gold";
    if (record.silver) return "silver";
    if (record.bronze) return "bronze";
    return null;
  }

  function isRuleMedalEarned(
    ruleOrId,
    tierKey = null
  ) {
    const record = medalRecordForRule(ruleOrId);

    if (tierKey) {
      return Boolean(record[tierKey]);
    }

    return Boolean(
      record.bronze ||
      record.silver ||
      record.gold
    );
  }

  function syncEarnedMedalsFromEvidence(
    achievedAt = null
  ) {
    const stamp =
      achievedAt ||
      new Date().toISOString();

    const newlyEarned = [];

    ALL_RANK_RULES.forEach((rule) => {
      const current = medalRecordForRule(rule);

      MEDAL_TIERS.forEach((tier) => {
        if (
          !current[tier.key] &&
          certificationRuleSatisfied(rule, tier.key)
        ) {
          current[tier.key] = stamp;
          newlyEarned.push({
            rankId: rule.id,
            trackKey: rule.trackKey,
            tierKey: tier.key
          });
        }
      });

      if (
        current.bronze ||
        current.silver ||
        current.gold
      ) {
        rankCertificationState.medalAchievedAt[rule.id] = current;
      }
    });

    if (newlyEarned.length) {
      saveRankCertificationState();
    }

    return newlyEarned;
  }

  function syncEarnedMedalsFromCurrentRank() {
    return syncEarnedMedalsFromEvidence();
  }

  function medalClassForTier(tierKey) {
    if (tierKey === "gold") return "medal-gold";
    if (tierKey === "silver") return "medal-silver";
    if (tierKey === "bronze") return "medal-bronze";
    return "";
  }

  function setMedalVisual(
    element,
    rankName,
    tierKey = null
  ) {
    if (!element) return;

    element.classList.remove(
      "rank-kyu-low",
      "rank-kyu-mid",
      "rank-kyu-high",
      "rank-dan-1",
      "rank-dan-2",
      "rank-dan-3",
      "rank-master",
      "medal-bronze",
      "medal-silver",
      "medal-gold",
      "no-rank"
    );

    const effectiveTier = tierKey || null;
    const hasRank = Boolean(
      rankName &&
      rankName !== "見習い" &&
      effectiveTier
    );

    if (!hasRank) {
      element.classList.add("no-rank");
    } else {
      const tierClass = medalClassForTier(effectiveTier);
      if (tierClass) element.classList.add(tierClass);
    }

    if (
      element.classList.contains(
        "home-rank-medal-coin"
      )
    ) {
      const image = element.querySelector(
        ".home-rank-medal-image"
      );

      const sourceMap = {
        gold: element.dataset.goldSrc,
        silver: element.dataset.silverSrc,
        bronze: element.dataset.bronzeSrc
      };

      if (
        hasRank &&
        image &&
        sourceMap[effectiveTier]
      ) {
        image.src = sourceMap[effectiveTier];
        image.alt = `${getMedalTierDefinition(effectiveTier).label}メダル`;
        element.title = `${rankName}・${getMedalTierDefinition(effectiveTier).label}メダル`;
      } else if (image) {
        image.removeAttribute("src");
        image.alt = "未獲得";
        element.title = "まだメダルを獲得していません";
      }

      return;
    }

    const textNode = element.querySelector(
      ".rank-medal-text"
    );

    if (textNode) {
      textNode.textContent =
        rankName === "見習い" || !rankName
          ? "－"
          : rankName;
    }
  }

  function formatMedalDate(iso) {
    if (!iso) return "";

    try {
      return new Date(iso).toLocaleDateString(
        "ja-JP",
        {
          year: "numeric",
          month: "numeric",
          day: "numeric"
        }
      );
    } catch (error) {
      return "";
    }
  }

  function actualTrackPosition(trackKey) {
    const track = trackForKey(trackKey);
    let rankIndex = -1;
    let tierKey = null;

    track?.ranks.forEach((rule, index) => {
      const tier = highestMedalTierForRule(rule);

      if (tier) {
        rankIndex = index;
        tierKey = tier;
      }
    });

    return { rankIndex, tierKey };
  }

  function compareTrackPositions(a, b) {
    const left = a || { rankIndex: -1, tierKey: null };
    const right = b || { rankIndex: -1, tierKey: null };

    if (left.rankIndex !== right.rankIndex) {
      return left.rankIndex - right.rankIndex;
    }

    return (
      (MEDAL_TIER_ORDER[left.tierKey] ?? -1) -
      (MEDAL_TIER_ORDER[right.tierKey] ?? -1)
    );
  }

  function nextTrackMedalGoal(trackKey, current) {
    const track = trackForKey(trackKey);

    if (!track) return null;

    if (!current || current.rankIndex < 0) {
      return {
        track,
        rule: track.ranks[0],
        tier: getMedalTierDefinition("bronze"),
        catchup: false
      };
    }

    const currentRule = track.ranks[current.rankIndex];
    const currentTierKey = normalizeTierKey(current.tierKey);

    if (
      !certificationRuleSatisfied(
        currentRule,
        currentTierKey
      )
    ) {
      return {
        track,
        rule: currentRule,
        tier: getMedalTierDefinition(currentTierKey),
        catchup: true
      };
    }

    if (currentTierKey === "bronze") {
      return {
        track,
        rule: currentRule,
        tier: getMedalTierDefinition("silver"),
        catchup: false
      };
    }

    if (currentTierKey === "silver") {
      return {
        track,
        rule: currentRule,
        tier: getMedalTierDefinition("gold"),
        catchup: false
      };
    }

    const nextRule = track.ranks[current.rankIndex + 1];

    if (!nextRule) return null;

    return {
      track,
      rule: nextRule,
      tier: getMedalTierDefinition("bronze"),
      catchup: false
    };
  }

  function calculateTrackRank(trackKey) {
    const track = trackForKey(trackKey);
    const actual = actualTrackPosition(trackKey);
    const legacy =
      rankCertificationState.legacyFloorByTrack?.[trackKey] ||
      null;

    const legacyPosition = legacy
      ? {
          rankIndex: legacy.rankIndex,
          tierKey: legacy.tierKey
        }
      : {
          rankIndex: -1,
          tierKey: null
        };

    const useLegacy =
      compareTrackPositions(
        legacyPosition,
        actual
      ) > 0;

    const current = useLegacy
      ? legacyPosition
      : actual;

    const currentRule =
      current.rankIndex >= 0
        ? track.ranks[current.rankIndex]
        : null;

    const nextGoal = nextTrackMedalGoal(
      trackKey,
      current
    );

    return {
      track,
      rankIndex: current.rankIndex,
      name: currentRule?.name || "見習い",
      currentRule,
      currentTierKey: current.tierKey,
      currentTierLabel: current.tierKey
        ? getMedalTierDefinition(current.tierKey).label
        : null,
      legacyRetained: useLegacy,
      legacySourceRank:
        useLegacy
          ? legacy?.sourceRank || "旧認定"
          : null,
      currentEvidence:
        currentRule && current.tierKey
          ? certificationEvidenceText(
              currentRule,
              current.tierKey
            )
          : "",
      nextGoal,
      nextProgress:
        nextGoal
          ? certificationRuleProgress(
              nextGoal.rule,
              nextGoal.tier.key
            )
          : 100
    };
  }

  function displayTrackRankLabel(rank) {
    return rank.currentTierLabel
      ? `${rank.name}（${rank.currentTierLabel}）`
      : rank.name;
  }

  function trackNextText(rank) {
    const goal = rank.nextGoal;

    if (!goal) {
      return "この系統の全金条件を達成しています";
    }

    if (goal.catchup) {
      return `旧認定を維持中｜次へ進むには${goal.rule.name} ${goal.tier.label}条件を補完`;
    }

    return `次は ${goal.rule.name} ${goal.tier.label}メダル`;
  }

  function displayedTierForRule(rule) {
    const actualTier = highestMedalTierForRule(rule);
    const legacy =
      rankCertificationState.legacyFloorByTrack?.[
        rule.trackKey
      ];

    if (
      legacy &&
      legacy.rankIndex === rule.index
    ) {
      const legacyTier = normalizeTierKey(
        legacy.tierKey
      );

      if (
        !actualTier ||
        MEDAL_TIER_ORDER[legacyTier] >
          MEDAL_TIER_ORDER[actualTier]
      ) {
        return {
          tierKey: legacyTier,
          legacy: true
        };
      }
    }

    return {
      tierKey: actualTier,
      legacy: false
    };
  }

  function renderMedalCollection(...args) {
    return appDiagnostics.measure("renderMedalCollection", () => renderMedalCollectionMeasured.apply(this,args));
  }
  function renderMedalCollectionMeasured() {
    if (!medalCollectionGrid) return;

    medalCollectionGrid.innerHTML = "";

    Object.values(RANK_TRACKS).forEach((track) => {
      const heading = document.createElement("div");
      heading.className = "medal-track-heading";
      heading.textContent = track.label;
      medalCollectionGrid.appendChild(heading);

      track.ranks.forEach((rank) => {
        const display = displayedTierForRule(rank);
        const tierKey = display.tierKey;
        const earned = Boolean(tierKey);
        const record = medalRecordForRule(rank);
        const tier = tierKey
          ? getMedalTierDefinition(tierKey)
          : null;

        const slot = document.createElement("div");
        slot.className = `medal-slot ${earned ? "earned" : "locked"}`;

        const medal = document.createElement("img");
        medal.className = "collection-medal-image";
        const currentMedals = $(".home-rank-medal-coin").dataset;
        const sourceMap = {
          gold: currentMedals.goldSrc,
          silver: currentMedals.silverSrc,
          bronze: currentMedals.bronzeSrc
        };
        medal.src = sourceMap[tierKey] || sourceMap.gold;
        medal.alt = tier ? `${rank.name}・${tier.label}メダル` : `${rank.name}・未獲得`;
        medal.width = 72;
        medal.height = 72;

        const name = document.createElement("div");
        name.className = "medal-slot-name";
        name.textContent = tier
          ? `${rank.name}・${tier.label}`
          : rank.name;

        const status = document.createElement("div");
        status.className = "medal-slot-status";

        if (display.legacy) {
          status.textContent =
            `旧認定引継ぎ｜次へ進むには新体系の金条件を補完`;
        } else if (tier) {
          status.textContent =
            `${tier.label}メダル獲得 ${formatMedalDate(record[tier.key])}`;
        } else {
          status.textContent = "未獲得";
        }

        slot.appendChild(medal);
        slot.appendChild(name);
        slot.appendChild(status);
        medalCollectionGrid.appendChild(slot);
      });
    });
  }

  function medalRequirementText(rankRule, tierKey) {
    const tier = getMedalTierDefinition(tierKey);
    const priorText = rankRule?.priorModes?.length
      ? "それ以前の全モードを金条件で達成し、"
      : "";

    return tier.timedOnly
      ? `${priorText}現在の対象モードを5分以内に${tier.minCorrect}/12以上`
      : `${priorText}現在の対象モードを${tier.minCorrect}/12以上`;
  }

  function renderMedalConditions() {
    if (!medalConditionList) return;

    medalConditionList.innerHTML = "";

    Object.values(RANK_TRACKS).forEach((track) => {
      const heading = document.createElement("div");
      heading.className = "medal-track-heading";
      heading.textContent = track.label;
      medalConditionList.appendChild(heading);

      track.ranks.forEach((rule) => {
        const display = displayedTierForRule(rule);
        const tierKey = display.tierKey;
        const tier = tierKey
          ? getMedalTierDefinition(tierKey)
          : null;

        const row = document.createElement("div");
        row.className =
          `medal-condition-row ${tier ? "earned" : ""}`;

        const rank = document.createElement("div");
        rank.className = "medal-condition-rank";
        rank.textContent = rule.name;

        const condition = document.createElement("div");
        condition.className = "medal-condition-text";
        condition.textContent =
          `${rule.requirement}｜上位認定には、それ以前の全モードで金が必要`;

        const status = document.createElement("div");
        status.className = "medal-condition-status";
        status.textContent = display.legacy
          ? `${tier?.label || "銅"}・旧認定引継ぎ`
          : tier
            ? `${tier.label}獲得済み`
            : `銅まで ${Math.round(
                certificationRuleProgress(
                  rule,
                  "bronze"
                )
              )}%`;

        row.appendChild(rank);
        row.appendChild(condition);
        row.appendChild(status);
        medalConditionList.appendChild(row);
      });
    });
  }

  let medalResetArmedUntil = 0;
  let medalResetDisarmTimer = null;

  function setMedalResetUi(
    armed = false,
    message = ""
  ) {
    if (medalResetBtn) {
      medalResetBtn.classList.toggle(
        "armed",
        armed
      );

      medalResetBtn.textContent = armed
        ? "もう一度押してリセット"
        : "メダルをリセット";
    }

    if (medalResetStatus) {
      medalResetStatus.textContent = message;
    }
  }

  function disarmMedalReset() {
    medalResetArmedUntil = 0;

    if (medalResetDisarmTimer) {
      clearTimeout(medalResetDisarmTimer);
      medalResetDisarmTimer = null;
    }

    setMedalResetUi(false, "");
  }

  function resetMedalProgress() {
    const stamp = new Date().toISOString();

    rankCertificationState =
      emptyRankCertificationState(stamp);

    saveRankCertificationState();
    closeRankCelebration();
    updateRankUi();

    setMedalResetUi(
      false,
      "2系統のメダルと旧認定引継ぎをリセットしました。"
    );

    medalResetArmedUntil = 0;

    if (medalResetDisarmTimer) {
      clearTimeout(medalResetDisarmTimer);
      medalResetDisarmTimer = null;
    }
  }

  function handleMedalResetClick() {
    const now = Date.now();

    if (medalResetArmedUntil > now) {
      resetMedalProgress();
      return;
    }

    medalResetArmedUntil = now + 6000;

    setMedalResetUi(
      true,
      "誤操作防止のため、6秒以内にもう一度押してください。"
    );

    if (medalResetDisarmTimer) {
      clearTimeout(medalResetDisarmTimer);
    }

    medalResetDisarmTimer = setTimeout(
      disarmMedalReset,
      6200
    );
  }

  function buildRankConfetti() {
    if (!rankConfettiLayer) return;

    rankConfettiLayer.innerHTML = "";

    const colors = [
      "#f2c84b",
      "#ef7d67",
      "#6fc2d0",
      "#8d86d8",
      "#8cc36f",
      "#ffffff"
    ];

    for (let i = 0; i < 42; i += 1) {
      const piece = document.createElement("div");
      piece.className = "rank-confetti";
      piece.style.left = `${(i * 37) % 100}%`;
      piece.style.background = colors[i % colors.length];
      piece.style.setProperty(
        "--delay",
        `${(i % 9) * -0.23}s`
      );
      piece.style.setProperty(
        "--fall",
        `${2.2 + (i % 7) * 0.18}s`
      );
      piece.style.setProperty(
        "--drift",
        `${-55 + (i % 11) * 11}px`
      );
      rankConfettiLayer.appendChild(piece);
    }
  }

  function closeRankCelebration() {
    if (!rankCelebration) return;

    rankCelebration.classList.remove("show");
    rankCelebration.setAttribute(
      "aria-hidden",
      "true"
    );

    if (rankConfettiLayer) {
      rankConfettiLayer.innerHTML = "";
    }
  }

  function showRankCelebration(
    rankId,
    tierKey,
    newlyEarned = []
  ) {
    const rule = ruleForId(rankId);

    if (!rankCelebration || !rule) return;

    const tier = getMedalTierDefinition(tierKey);

    setMedalVisual(
      rankCelebrationMedal,
      rule.name,
      tier.key
    );

    rankCelebrationMedalText.textContent = rule.name;
    rankCelebrationTitle.textContent =
      `${rule.trackLabel} ${rule.name} ${tier.label}メダル獲得！`;

    const conditionText = medalRequirementText(
      rule,
      tier.key
    );

    rankCelebrationSub.textContent =
      newlyEarned.length > 1
        ? `${conditionText} 今回は${newlyEarned.length}段階のメダル条件を達成しました。`
        : `${conditionText}を達成しました。`;

    buildRankConfetti();
    rankCelebration.classList.add("show");
    rankCelebration.setAttribute(
      "aria-hidden",
      "false"
    );

    if (
      "speechSynthesis" in window &&
      typeof SpeechSynthesisUtterance !== "undefined"
    ) {
      try {
        const utterance =
          new SpeechSynthesisUtterance(
            `メダル獲得！${rule.trackLabel}、${rule.name}、${tier.label}メダル、おめでとう！`
          );

        utterance.lang = "ja-JP";
        utterance.rate = 0.95;
        utterance.pitch = 1.08;
        utterance.volume = appMasterVolume;

        const voice = getJapaneseVoice();
        if (voice) utterance.voice = voice;

        speakWithAppVolume(utterance);
      } catch (error) {}
    }
  }

  function refreshNextRankGuide() {
    if (
      !nextRankGuide ||
      !nextRankGuideTitle ||
      !nextRankGuideText
    ) {
      return;
    }

    root.querySelectorAll(
      ".mode-card.rank-recommended"
    ).forEach((card) => {
      card.classList.remove("rank-recommended");
    });

    root.querySelectorAll(
      ".rank-recommend-chip"
    ).forEach((chip) => chip.remove());

    nextRankGuideTitle.textContent =
      "次の級・段まで";

    nextRankGuideText.innerHTML = "";

    Object.keys(RANK_TRACKS).forEach((trackKey) => {
      const rank = calculateTrackRank(trackKey);
      const goal = rank.nextGoal;
      const section = document.createElement("section");
      section.className = "rank-track-goal-section";

      const title = document.createElement("div");
      title.className = "rank-track-goal-title";
      title.textContent = goal
        ? `${rank.track.label}：${goal.rule.name} ${goal.tier.label}メダルまで`
        : `${rank.track.label}：全金条件達成`;

      section.appendChild(title);

      if (!goal) {
        const complete = document.createElement("div");
        complete.className = "rank-goal-summary";
        complete.textContent =
          "この系統の全モードで金条件を達成しています。";
        section.appendChild(complete);
        nextRankGuideText.appendChild(section);
        return;
      }

      const summary = document.createElement("div");
      summary.className = "rank-goal-summary";
      summary.textContent = goal.catchup
        ? `旧認定は維持します。次の級・段へ進むには、追加されたモードを含め${goal.rule.name}までの条件を補完してください。`
        : medalRequirementText(
            goal.rule,
            goal.tier.key
          );

      const list = document.createElement("div");
      list.className = "rank-goal-list";

      const rows = goalRequirementRows(
        goal.rule,
        goal.tier.key
      );

      rows.forEach((rowInfo) => {
        const tier = getMedalTierDefinition(
          rowInfo.tierKey
        );

        const best = bestCorrectForMode(
          rowInfo.mode,
          tier.timedOnly
        );

        const done = best >= tier.minCorrect;
        if (done) return;
        const row = document.createElement("div");
        row.className =
          `rank-goal-row ${done ? "done" : ""}`;

        const op = document.createElement("div");
        op.className = "rank-goal-op";
        op.textContent = operationLabelForMode(
          rowInfo.mode
        );

        const modeText = document.createElement("div");
        modeText.className = "rank-goal-mode";
        modeText.textContent = shortModeName(
          rowInfo.mode
        );

        const status = document.createElement("div");
        status.className = "rank-goal-status";
        status.textContent = done
          ? `達成済み ${best}/12`
          : `最高${best}/12 → ${tier.label} ${tier.minCorrect}/12以上${tier.timedOnly ? "・5分以内" : ""}`;

        row.appendChild(op);
        row.appendChild(modeText);
        row.appendChild(status);
        list.appendChild(row);

        if (!done) {
          const button = root.querySelector(
            `.start-mode[data-mode="${rowInfo.mode}"]`
          );
          const card = button?.closest(".mode-card");

          if (card) {
            card.classList.add("rank-recommended");

            const chips = card.querySelector(".chips");

            if (
              chips &&
              !chips.querySelector(
                `.rank-recommend-chip[data-track="${trackKey}"]`
              )
            ) {
              const chip = document.createElement("span");
              chip.className = "chip rank-recommend-chip";
              chip.dataset.track = trackKey;
              chip.textContent =
                `${rank.track.shortLabel} ${goal.rule.name} ${goal.tier.label}に必要`;
              chips.prepend(chip);
            }
          }
        }
      });

      section.appendChild(summary);
      section.appendChild(list);
      nextRankGuideText.appendChild(section);
    });
  }

  function updateRankUi() {
    const addsub = calculateTrackRank("addsub");
    const muldiv = calculateTrackRank("muldiv");

    const addsubLabel = displayTrackRankLabel(addsub);
    const muldivLabel = displayTrackRankLabel(muldiv);

    if (appRankBadge) {
      appRankBadge.textContent =
        `足・引 ${addsubLabel}｜掛・割 ${muldivLabel}`;
    }

    if (appRankMeterFill) {
      appRankMeterFill.style.width =
        `${(
          (addsub.nextProgress + muldiv.nextProgress) /
          2
        ).toFixed(1)}%`;
    }

    if (appRankSub) {
      appRankSub.textContent =
        `足し算・引き算：${addsubLabel}｜掛け算・割り算：${muldivLabel}`;
    }

    if (appRankNext) {
      appRankNext.textContent =
        `足・引：${trackNextText(addsub)} ／ 掛・割：${trackNextText(muldiv)}`;
    }

    const activeTrackKey =
      trackKeyForMode(currentMode) ||
      "addsub";

    const activeRank =
      activeTrackKey === "muldiv"
        ? muldiv
        : addsub;

    if (resultRankTitle) {
      resultRankTitle.textContent =
        `${activeRank.track.label} ${displayTrackRankLabel(activeRank)}`;
    }

    if (resultRankProgress) {
      resultRankProgress.textContent =
        activeRank.nextGoal
          ? `${activeRank.nextGoal.rule.name} ${activeRank.nextGoal.tier.label}まで`
          : "全金条件達成";
    }

    if (homeAddSubRankName) {
      homeAddSubRankName.textContent = addsubLabel;
    }

    if (homeAddSubRankNext) {
      homeAddSubRankNext.textContent = trackNextText(addsub);
    }

    if (homeMulDivRankName) {
      homeMulDivRankName.textContent = muldivLabel;
    }

    if (homeMulDivRankNext) {
      homeMulDivRankNext.textContent = trackNextText(muldiv);
    }

    setMedalVisual(
      homeAddSubMedal,
      addsub.name,
      addsub.currentTierKey
    );

    setMedalVisual(
      homeMulDivMedal,
      muldiv.name,
      muldiv.currentTierKey
    );

    renderMedalCollection();
    renderMedalConditions();
    refreshNextRankGuide();

    return {
      addsub,
      muldiv
    };
  }

  function loadLearningStats() {
    try {
      const raw = localStorage.getItem(LEARNING_STORAGE_KEY);
      if (!raw) {
        return { problems: {} };
      }

      const parsed = JSON.parse(raw);
      if (!parsed || typeof parsed !== "object") {
        return { problems: {} };
      }

      if (!parsed.problems || typeof parsed.problems !== "object") {
        parsed.problems = {};
      }

      return parsed;
    } catch (error) {
      return { problems: {} };
    }
  }

  function saveLearningStats() {
    try {
      localStorage.setItem(
        LEARNING_STORAGE_KEY,
        JSON.stringify(learningStats)
      );
    } catch (error) {
      // 保存できない環境でもゲーム自体は継続する。
    }
  }

  function problemKey(mode, q) {
    return `${mode}|${questionOperators(q).join(",")}|${questionTerms(q).join(",")}`;
  }

  function getProblemStat(mode, q) {
    const key = problemKey(mode, q);

    if (!learningStats.problems[key]) {
      learningStats.problems[key] = {
        key,
        mode,
        a: q.a,
        b: q.b,
        op: q.op,
        terms: questionTerms(q),
        operators: questionOperators(q),
        formula: questionFormula(q, false),
        answer: q.answer,
        attempts: 0,
        correct: 0,
        wrong: 0,
        hints: 0,
        recoveryStreak: 0,
        mastered: false,
        lastAt: 0
      };
    }

    const stat =
      learningStats.problems[key];

    if (!Array.isArray(stat.terms)) {
      stat.terms = questionTerms(q);
      stat.operators = questionOperators(q);
      stat.formula = questionFormula(q, false);
      stat.answer = q.answer;
    }

    return stat;
  }

  function ensureQuestionTiming(
    questionIndex
  ) {
    if (!questionTimingLog[questionIndex]) {
      questionTimingLog[questionIndex] = {
        startPerf: null,
        responseMs: null,
        hintCount: 0,
        hintQuestionAttempts: 0,
        hintQuestionCorrectCount: 0,
        hintQuestionWrongCount: 0
      };
    }

    return questionTimingLog[questionIndex];
  }

  function markQuestionDisplayed(
    questionIndex
  ) {
    const timing =
      ensureQuestionTiming(
        questionIndex
      );

    if (timing.startPerf === null) {
      timing.startPerf =
        performance.now();
    }
  }

  function markQuestionAnswered(
    questionIndex
  ) {
    const timing =
      ensureQuestionTiming(
        questionIndex
      );

    if (timing.startPerf !== null) {
      timing.responseMs =
        Math.max(
          0,
          performance.now() -
            timing.startPerf
        );
    }
  }

  function markQuestionHintUsed(
    questionIndex
  ) {
    const timing =
      ensureQuestionTiming(
        questionIndex
      );

    timing.hintCount += 1;
  }

  function markHintQuestionResult(
    questionIndex,
    ok
  ) {
    const timing =
      ensureQuestionTiming(
        questionIndex
      );

    timing.hintQuestionAttempts += 1;

    if (ok) {
      timing.hintQuestionCorrectCount += 1;
    } else {
      timing.hintQuestionWrongCount += 1;
    }
  }

  function questionPointsForAnswer(
    entry,
    questionIndex
  ) {
    if (!entry?.ok) {
      return 0;
    }

    const timing =
      questionTimingLog[
        questionIndex
      ] || {};

    const hintUsed =
      (Number(timing.hintCount) || 0) > 0;

    // 珠ヒントなしで正解：5点
    if (!hintUsed) {
      return 5;
    }

    // 珠ヒント内の問いに1回でも間違えた後、最終回答が正解：3点
    if (
      (Number(
        timing.hintQuestionWrongCount
      ) || 0) > 0
    ) {
      return 3;
    }

    // 珠ヒントを使用し、問いで間違えず最終回答が正解：4点
    // （補数問題がないヒントも「問いで間違いなし」として4点）
    return 4;
  }

  function recordAnswer(
    mode,
    q,
    ok,
    hintUsed = false
  ) {
    const stat = getProblemStat(mode, q);

    stat.attempts += 1;
    stat.lastAt = Date.now();
    stat.hints =
      Number(stat.hints) || 0;

    // 珠ヒントを使った問題は、正解・不正解のどちらにも入れない。
    if (hintUsed) {
      stat.hints += 1;
      saveLearningStats();
      return;
    }

    if (ok) {
      stat.correct += 1;

      if (q.isWeakness) {
        stat.recoveryStreak += 1;

        if (
          stat.recoveryStreak >=
          RECOVERY_STREAK_TO_MASTER
        ) {
          stat.mastered = true;
        }
      }
    } else {
      stat.wrong += 1;
      stat.recoveryStreak = 0;
      stat.mastered = false;
    }

    saveLearningStats();
  }

  function getWeakCandidates(mode) {
    return Object.values(learningStats.problems)
      .filter((stat) =>
        stat.mode === mode &&
        stat.wrong > 0 &&
        !stat.mastered &&
        questionMatchesMode(mode, stat)
      )
      .sort((a, b) => {
        const scoreA =
          a.wrong * 4 -
          a.correct +
          Math.max(0, 2 - a.recoveryStreak) * 2;

        const scoreB =
          b.wrong * 4 -
          b.correct +
          Math.max(0, 2 - b.recoveryStreak) * 2;

        if (scoreB !== scoreA) {
          return scoreB - scoreA;
        }

        return b.lastAt - a.lastAt;
      });
  }

  function loadChallengeResumeState() {
    try {
      const raw =
        localStorage.getItem(
          CHALLENGE_RESUME_STORAGE_KEY
        );

      if (!raw) {
        return null;
      }

      const parsed =
        JSON.parse(raw);

      if (
        !parsed ||
        typeof parsed !== "object" ||
        !modeInfo[parsed.currentMode] ||
        !Number.isInteger(
          Number(parsed.index)
        )
      ) {
        return null;
      }

      const savedAt =
        Date.parse(
          parsed.savedAt || ""
        );

      if (
        Number.isFinite(savedAt) &&
        Date.now() - savedAt >
          14 * 24 * 60 * 60 * 1000
      ) {
        localStorage.removeItem(
          CHALLENGE_RESUME_STORAGE_KEY
        );
        return null;
      }

      return parsed;
    } catch (error) {
      return null;
    }
  }

  function clearChallengeResumeState() {
    try {
      localStorage.removeItem(
        CHALLENGE_RESUME_STORAGE_KEY
      );
    } catch (error) {}

    renderChallengeResumeCard();
  }

  function saveChallengeResumeState(
    nextIndexOverride = null
  ) {
    if (
      !currentMode ||
      activeRemedialSkillId ||
      results.classList.contains(
        "show"
      ) ||
      !workspace.classList.contains(
        "show"
      )
    ) {
      return;
    }

    const savedIndex =
      nextIndexOverride === null
        ? index
        : Number(
            nextIndexOverride
          );

    const safeTiming =
      questionTimingLog.map(
        (item) => {
          if (!item) {
            return item;
          }

          return {
            ...item,
            startPerf: null
          };
        }
      );

    const state = {
      version: 1,
      savedAt:
        new Date().toISOString(),
      currentMode,
      stampAttempt: mainStampAttempt,
      activeWeaknessChallengeMode,
      sessionTotalQuestions,
      index:
        Math.max(
          0,
          Math.min(
            sessionTotalQuestions,
            savedIndex
          )
        ),
      score,
      questions,
      answers,
      seconds,
      timeLimitEnabled: true,
      correctStreak,
      maxCorrectStreak,
      sessionWeakAsked,
      sessionWeakCorrect,
      questionTimingLog:
        safeTiming,
      voiceAnswerEnabled
    };

    try {
      localStorage.setItem(
        CHALLENGE_RESUME_STORAGE_KEY,
        JSON.stringify(state)
      );
    } catch (error) {}

    renderChallengeResumeCard();
  }

  function renderChallengeResumeCard() {
    if (
      !challengeResumeCard ||
      !challengeResumeText
    ) {
      return;
    }

    const state =
      loadChallengeResumeState();

    if (!state) {
      challengeResumeCard.classList.add(
        "hidden"
      );
      return;
    }

    const total =
      Math.max(
        1,
        Math.min(
          TOTAL_QUESTIONS,
          Number(
            state.sessionTotalQuestions
          ) || TOTAL_QUESTIONS
        )
      );

    const nextQuestion =
      Math.min(
        total,
        Number(state.index) + 1
      );

    const title =
      state.activeWeaknessChallengeMode
        ? `苦手克服｜${shortModeName(state.currentMode)}`
        : modeInfo[state.currentMode]?.title ||
          state.currentMode;

    challengeResumeText.textContent =
      `${title}｜${nextQuestion}/${total}問目から再開｜現在${Number(state.score) || 0}問正解`;

    challengeResumeCard.classList.remove(
      "hidden"
    );
  }

  function resumeSavedChallenge() {
    const state =
      loadChallengeResumeState();

    if (!state) {
      renderChallengeResumeCard();
      return;
    }

    resetSessionVideoData();

    startMode(
      state.currentMode,
      {
        resumeState: state
      }
    );
  }

  function renderWeaknessChallengeGrid() {
    if (!weaknessChallengeGrid) {
      return;
    }

    weaknessChallengeGrid.innerHTML = "";

    MODE_GROUPS.forEach((group) => {
      const wrapper =
        document.createElement(
          "section"
        );
      wrapper.className =
        "weakness-group mode-section-anchor";
      wrapper.id =
        `weak-${group.key}`;

      const heading =
        document.createElement("h3");
      heading.className =
        "weakness-group-title";
      heading.textContent =
        group.title;

      const grid =
        document.createElement("div");
      grid.className =
        "mode-grid";

      group.modes.forEach((mode) => {
        const candidates =
          getWeakCandidates(mode);

        const card =
          document.createElement(
            "article"
          );
        card.className =
          `mode-card weakness-mode-card ${candidates.length ? "" : "unavailable"}`;

        const examples =
          candidates
            .slice(0, 3)
            .map(
              (stat) =>
                stat.formula ||
                questionFormula(stat, false)
            )
            .join("、");

        card.innerHTML = `
          <div class="mode-no">${group.title}</div>
          <div class="mode-name">${shortModeName(mode)}</div>
          <div class="mode-desc">${
            candidates.length
              ? `未克服 ${candidates.length}問${examples ? `｜${examples}` : ""}`
              : "未克服の問題はありません"
          }</div>
          <div class="chips"><span class="chip">最大12問</span><span class="chip">5分計測</span></div>
        `;

        const button =
          document.createElement(
            "button"
          );
        button.type =
          "button";
        button.className =
          candidates.length
            ? "primary"
            : "";
        button.disabled =
          !candidates.length;
        button.textContent =
          candidates.length
            ? "苦手克服をはじめる"
            : "現在は選択できません";

        if (candidates.length) {
          button.addEventListener(
            "click",
            () => {
              startWeaknessChallenge(
                mode
              );
            }
          );
        }

        card.appendChild(button);
        grid.appendChild(card);
      });

      wrapper.appendChild(heading);
      wrapper.appendChild(grid);
      weaknessChallengeGrid.appendChild(
        wrapper
      );
    });
  }

  function startWeaknessChallenge(
    mode
  ) {
    const candidates =
      getWeakCandidates(mode)
        .slice(
          0,
          TOTAL_QUESTIONS
        );

    if (!candidates.length) {
      renderWeaknessChallengeGrid();
      return;
    }

    const presetQuestions =
      candidates.map(
        (stat) =>
          statToWeakQuestion(
            stat
          )
      );

    resetSessionVideoData();

    startMode(
      mode,
      {
        weaknessChallengeMode:
          mode,
        presetQuestions,
        totalQuestions:
          presetQuestions.length
      }
    );
  }

  function refreshChallengeMenuUi() {
    renderChallengeResumeCard();
    refreshNextRankGuide();
  }

  function statToWeakQuestion(stat) {
    const q =
      Array.isArray(stat.terms) &&
      stat.terms.length > 2
        ? makeSequenceQuestion(
            stat.terms,
            stat.op
          )
        : makeQuestionFromFinal(
            stat.a,
            stat.op,
            stat.b
          );

    q.isWeakness = true;
    q.weaknessKey = stat.key;

    return q;
  }

  function makeQuestionFromFinal(a, op, b) {
    const q = {
      a,
      op,
      b,
      answer: calculate(a, op, b),
      isWeakness: false,
      weaknessKey: null
    };

    if (!isValidQuestion(q)) {
      throw new Error(
        `苦手問題の復元に失敗: ${a} ${op} ${b}`
      );
    }

    return q;
  }

  function getWeaknessQuestion(mode) {
    const active = getWeakCandidates(mode);

    // 未克服の苦手だけを出題する。
    // 苦手克服問題として1回正解して mastered=true になった問題は
    // getWeakCandidates() の対象外になるため、二度と苦手枠には出ない。
    if (active.length === 0) {
      return null;
    }

    const source = active[0];

    return statToWeakQuestion(source);
  }

  function makeFinalQuestion(
    a,
    op,
    b
  ) {
    const q = {
      a,
      op,
      b,
      answer: calculate(a, op, b),
      isWeakness: false,
      weaknessKey: null
    };

    if (!isValidQuestion(q)) {
      throw new Error(
        `補習問題生成失敗: ${a} ${op} ${b}`
      );
    }

    return q;
  }

  function makeRemedialQuestion(
    skillId
  ) {
    for (
      let tries = 0;
      tries < 200;
      tries += 1
    ) {
      let q = null;

      if (skillId === "add_direct") {
        const a = randInt(1, 3);
        const b = randInt(1, Math.max(1, 4 - a));
        q = makeFinalQuestion(a, "＋", b);
      } else if (skillId === "add_five") {
        const a = randInt(1, 4);
        const b = randInt(1, 4);

        if (a + b >= 5 && a + b <= 8) {
          q = makeFinalQuestion(a, "＋", b);
        }
      } else if (skillId === "add_ten") {
        const a = randInt(6, 9);
        const b = randInt(2, 9);

        if (a + b >= 10) {
          q = makeFinalQuestion(a, "＋", b);
        }
      } else if (skillId === "add_multi") {
        const a = randInt(20, 69);
        const b = randInt(10, 29);

        if (
          a + b <= 99 &&
          (a % 10) + (b % 10) >= 10
        ) {
          q = makeFinalQuestion(a, "＋", b);
        }
      } else if (skillId === "sub_direct") {
        const a = randInt(3, 9);
        const b = randInt(1, Math.min(4, a - 1));

        if (
          !(
            a >= 5 &&
            b < 5 &&
            (a % 5) < b
          )
        ) {
          q = makeFinalQuestion(a, "－", b);
        }
      } else if (skillId === "sub_five") {
        const a = randInt(5, 9);
        const b = randInt(1, 4);

        if ((a % 5) < b) {
          q = makeFinalQuestion(a, "－", b);
        }
      } else if (skillId === "sub_ten") {
        const ones = randInt(0, 8);
        const a = 10 + ones;
        const b = randInt(
          ones + 1,
          9
        );
        q = makeFinalQuestion(a, "－", b);
      } else if (skillId === "sub_multi") {
        const a = randInt(30, 99);
        const b = randInt(10, a - 1);

        if (
          (a % 10) < (b % 10)
        ) {
          q = makeFinalQuestion(a, "－", b);
        }
      } else if (skillId === "mul_basic") {
        q = makeFinalQuestion(
          randInt(1, 9),
          "×",
          randInt(1, 9)
        );
      } else if (skillId === "mul_place") {
        q = makeFinalQuestion(
          randInt(10, 99),
          "×",
          randInt(2, 9)
        );
      } else if (skillId === "div_basic") {
        const divisor = randInt(2, 9);
        const quotient = randInt(1, 9);
        q = makeFinalQuestion(
          divisor * quotient,
          "÷",
          divisor
        );
      } else if (skillId === "div_place") {
        const divisor = randInt(2, 9);
        const quotient = randInt(12, 99);
        q = makeFinalQuestion(
          divisor * quotient,
          "÷",
          divisor
        );
      }

      if (q) {
        q.remedialSkillId = skillId;
        return q;
      }
    }

    return makeOneQuestion(
      SKILL_DEFS[skillId]?.baseMode ||
      currentMode ||
      "ba1"
    );
  }

  function startRemedialPractice(
    skillId
  ) {
    const def =
      SKILL_DEFS[skillId];

    if (!def) {
      return;
    }

    // 補習は録画なし。5分は計測しますが、0:00でも最後まで続けます。
    resetSessionVideoData();

    startMode(
      def.baseMode,
      {
        remedialSkillId:
          skillId
      }
    );
  }

  function openSkillLesson(
    skillId
  ) {
    const def =
      SKILL_DEFS[skillId];

    if (!def) {
      return;
    }

    showLearningHome();

    openLearningLesson(
      def.category,
      def.lessonIndex
    );
  }

  function makeQuestionForIndex(questionIndex, mode) {
    if (activeRemedialSkillId) {
      return makeRemedialQuestion(
        activeRemedialSkillId
      );
    }

    // 1〜5問目は必ず通常問題。
    if (questionIndex < 5) {
      const q = makeOneQuestion(mode);
      q.isWeakness = false;
      return q;
    }

    // 6問目以降の指定スロットでは苦手問題を優先。
    if (WEAKNESS_SLOTS.has(questionIndex)) {
      const weak = getWeaknessQuestion(mode);

      if (weak) {
        sessionWeakAsked += 1;
        return weak;
      }
    }

    const q = makeOneQuestion(mode);
    q.isWeakness = false;
    return q;
  }

  function shouldLevelUp(mode, finalScore) {
    const activeWeakLeft = getWeakCandidates(mode).length;

    // 苦手克服問題が出た場合：
    // 出た苦手問題をすべてクリアし、未克服が残っておらず、
    // 全体でも10/12以上なら次のレベルへ。
    if (sessionWeakAsked > 0) {
      return (
        sessionWeakCorrect === sessionWeakAsked &&
        activeWeakLeft === 0 &&
        finalScore >= 10
      );
    }

    // 苦手が記録されていない場合は11/12以上でレベルアップ。
    return activeWeakLeft === 0 && finalScore >= 11;
  }

  function makeOneQuestion(mode) {
    if (mode === "ba1") return makeAdditionByOnesCarry(1, false);
    if (mode === "ba2") return makeAdditionByOnesCarry(1, true);
    if (mode === "ba2x4") return makeMultiAddition(4, 1, 9);
    if (mode === "ba3") return makeAdditionByOnesCarry(2, false);
    if (mode === "ba4") return makeAdditionByOnesCarry(2, true);
    if (mode === "ba4x4") return makeMultiAddition(4, 10, 99);
    if (mode === "ba5") return makeAdditionOnly(100, 999);
    if (mode === "ba5x4") return makeMultiAddition(4, 100, 999);

    if (mode === "bs1") return makeSubtractionByOnesBorrow(1, false);
    if (mode === "bs2") return makeSubtractionByOnesBorrow(1, true);
    if (mode === "bs2x4") return makeMultiSubtraction(4, 10, 99, 1, 9);
    if (mode === "bs3") return makeSubtractionByOnesBorrow(2, false);
    if (mode === "bs4") return makeSubtractionByOnesBorrow(2, true);
    if (mode === "bs4x4") return makeMultiSubtraction(4, 40, 99, 10, 39);
    if (mode === "bs5") return makeSubtractionOnly(100, 999);
    if (mode === "bs5x4") return makeMultiSubtraction(5, 500, 999, 10, 99);

    if (mode === "mm1") {
      return makeMul(1, 9, 1, 9);
    }

    if (mode === "mm2") {
      return makeMul(10, 99, 1, 9);
    }

    if (mode === "mm3") {
      return makeMul(10, 99, 10, 99);
    }

    if (mode === "md1") {
      return makeExactDivision(1, 81, 1, 9);
    }

    if (mode === "md2") {
      return makeExactDivision(100, 999, 1, 9);
    }

    if (mode === "md3") {
      return makeExactDivision(100, 999, 10, 99);
    }

    if (mode === "a1") return makeAddSub(1000, 9999);

    if (mode === "a2") {
      return coin()
        ? makeMul(100, 999, 10, 99)
        : makeExactDivision(1000, 9999, 10, 99);
    }

    return coin()
      ? makeMul(100, 999, 100, 999)
      : makeExactDivision(10000, 99999, 100, 999);
  }

  function generateQuestions(mode) {
    // 問題はセッション中に1問ずつ生成する。
    // これにより最初の5問で見つかった苦手も、
    // 6問目以降の苦手克服問題へ反映できる。
    return [];
  }

  function placeName(place) {
    const names = {
      1: "一の位",
      10: "十の位",
      100: "百の位",
      1000: "千の位",
      10000: "万の位",
      100000: "十万の位",
      1000000: "百万の位"
    };

    return names[place] || `${place}の位`;
  }

  function shortPlaceName(place) {
    const names = {
      1: "一",
      10: "十",
      100: "百",
      1000: "千",
      10000: "万",
      100000: "十万",
      1000000: "百万"
    };

    return names[place] || "";
  }

  function buildSorobanBoard(digitCount) {
    hintDigitCount = Math.max(1, digitCount);
    hintRods = [];
    sorobanBoard.innerHTML = "";

    for (let i = 0; i < hintDigitCount; i += 1) {
      const place = 10 ** (hintDigitCount - 1 - i);

      const rod = document.createElement("div");
      rod.className = "soroban-rod";
      rod.dataset.place = String(place);

      const line = document.createElement("div");
      line.className = "rod-line";
      rod.appendChild(line);

      const upper = document.createElement("div");
      upper.className = "soroban-bead upper-bead";
      rod.appendChild(upper);

      const lowers = [];

      for (let j = 0; j < 4; j += 1) {
        const bead = document.createElement("div");
        bead.className = "soroban-bead lower-bead";
        bead.style.top = `${112 + j * 18}px`;
        rod.appendChild(bead);
        lowers.push(bead);
      }

      const label = document.createElement("div");
      label.className = "rod-place";
      label.textContent = shortPlaceName(place);
      rod.appendChild(label);

      sorobanBoard.appendChild(rod);

      hintRods.push({
        rod,
        place,
        upper,
        lowers,
        currentDigit: 0
      });
    }
  }

  function setRodDigit(rodInfo, digit) {
    const safeDigit = Math.max(0, Math.min(9, Number(digit) || 0));
    const upperOn = safeDigit >= 5;
    const lowerCount = safeDigit % 5;

    rodInfo.upper.style.top =
      upperOn ? "50px" : "13px";

    rodInfo.lowers.forEach((bead, index) => {
      const top = index < lowerCount
        ? 89 + index * 18
        : 121 + index * 18;

      bead.style.top = `${top}px`;
    });

    rodInfo.currentDigit = safeDigit;
  }

  function clearSorobanBeadGlow() {
    hintRods.forEach((rodInfo) => {
      rodInfo.upper.classList.remove(
        "used-glow"
      );

      rodInfo.lowers.forEach((bead) => {
        bead.classList.remove(
          "used-glow"
        );
      });
    });
  }

  function glowUsedBeads(
    rodInfo,
    digit
  ) {
    const safeDigit =
      Math.max(
        0,
        Math.min(
          9,
          Number(digit) || 0
        )
      );

    if (safeDigit >= 5) {
      rodInfo.upper.classList.add(
        "used-glow"
      );
    }

    const lowerCount =
      safeDigit % 5;

    rodInfo.lowers.forEach(
      (bead, index) => {
        if (index < lowerCount) {
          bead.classList.add(
            "used-glow"
          );
        }
      }
    );
  }

  function glowChangedBeads(
    rodInfo,
    beforeDigit,
    afterDigit
  ) {
    const beforeUpper =
      beforeDigit >= 5;

    const afterUpper =
      afterDigit >= 5;

    if (
      beforeUpper !==
      afterUpper
    ) {
      rodInfo.upper.classList.add(
        "used-glow"
      );
    }

    const beforeLower =
      beforeDigit % 5;

    const afterLower =
      afterDigit % 5;

    rodInfo.lowers.forEach(
      (bead, index) => {
        const beforeOn =
          index < beforeLower;

        const afterOn =
          index < afterLower;

        if (
          beforeOn !==
          afterOn
        ) {
          bead.classList.add(
            "used-glow"
          );
        }
      }
    );
  }

  function showSorobanNumber(
    value,
    activePlace = null,
    options = {}
  ) {
    const safeValue = Math.max(
      0,
      Math.floor(Math.abs(Number(value) || 0))
    );

    const digits = String(safeValue)
      .padStart(hintDigitCount, "0")
      .slice(-hintDigitCount)
      .split("")
      .map(Number);

    const beforeDigits =
      hintRods.map(
        (rodInfo) =>
          Number(
            rodInfo.currentDigit
          ) || 0
      );

    clearSorobanBeadGlow();

    hintRods.forEach((rodInfo, index) => {
      const nextDigit =
        digits[index];

      setRodDigit(
        rodInfo,
        nextDigit
      );

      rodInfo.rod.classList.toggle(
        "active",
        activePlace !== null &&
        rodInfo.place === activePlace
      );

      if (
        options.highlightAllUsed &&
        nextDigit > 0
      ) {
        glowUsedBeads(
          rodInfo,
          nextDigit
        );
      } else if (
        options.highlightUsed &&
        activePlace !== null &&
        rodInfo.place === activePlace
      ) {
        glowUsedBeads(
          rodInfo,
          nextDigit
        );
      } else if (
        options.highlightChanged &&
        activePlace !== null &&
        rodInfo.place === activePlace
      ) {
        glowChangedBeads(
          rodInfo,
          beforeDigits[index],
          nextDigit
        );
      }
    });
  }

  function decomposeByPlace(value) {
    const out = [];
    const digits = String(Math.abs(Math.floor(value))).split("");

    digits.forEach((char, index) => {
      const digit = Number(char);
      if (digit === 0) return;

      const place =
        10 ** (digits.length - 1 - index);

      out.push({
        digit,
        place,
        amount: digit * place
      });
    });

    return out;
  }

  function hintDigitAt(
    value,
    place
  ) {
    return Math.floor(
      Math.abs(value) /
      place
    ) % 10;
  }

  function pushHintMove(
    steps,
    state,
    delta,
    activePlace,
    text,
    extra = {}
  ) {
    state.value += delta;

    steps.push({
      value: state.value,
      activePlace,
      text,
      highlightChanged: true,
      ...extra
    });
  }

  function pushHintExplain(
    steps,
    state,
    activePlace,
    text,
    extra = {}
  ) {
    steps.push({
      value: state.value,
      activePlace,
      text,
      highlightUsed:
        activePlace !== null,
      ...extra
    });
  }

  function addWithinDigitHint(
    steps,
    state,
    place,
    amount,
    context = ""
  ) {
    if (amount <= 0) {
      return;
    }

    const digit =
      hintDigitAt(
        state.value,
        place
      );

    const prefix =
      context
        ? `${context} `
        : "";

    // 5以上を足す場合、五珠を使えるなら先に五珠。
    if (
      amount >= 5 &&
      digit < 5
    ) {
      const firstFiveAddText =
        context
          ? `${prefix}次に、${placeName(place)}で5を足します。`
          : `${placeName(place)}で、まず5を足します。`;

      pushHintMove(
        steps,
        state,
        5 * place,
        place,
        firstFiveAddText
      );

      const rest =
        amount - 5;

      if (rest > 0) {
        pushHintMove(
          steps,
          state,
          rest * place,
          place,
          `${placeName(place)}で、残りの${rest}を足します。`
        );
      }

      return;
    }

    // 5をまたぐ足し算。
    // 例: 2+4 → 先に-1、そのあと+5。
    // 説明だけのSTEPを挟まず、最初の珠移動と説明を1つにまとめる。
    if (
      digit < 5 &&
      amount < 5 &&
      digit + amount >= 5
    ) {
      const complement =
        5 - amount;

      pushHintMove(
        steps,
        state,
        -complement * place,
        place,
        `${placeName(place)}で5をまたぎます。${amount}を足すときに使う「5の補数」は${complement}です。先に${complement}を引きます。`
      );

      pushHintMove(
        steps,
        state,
        5 * place,
        place,
        `次に5を足します。${complement}を引いて5を足すと、合わせて${amount}を足したことになります。`
      );

      return;
    }

    pushHintMove(
      steps,
      state,
      amount * place,
      place,
      `${prefix}${placeName(place)}で${amount}をそのまま足します。`
    );
  }

  function subtractWithinDigitHint(
    steps,
    state,
    place,
    amount,
    context = ""
  ) {
    if (amount <= 0) {
      return;
    }

    const digit =
      hintDigitAt(
        state.value,
        place
      );

    const prefix =
      context
        ? `${context} `
        : "";

    if (
      digit >= 5 &&
      amount >= 5
    ) {
      const firstFiveSubtractText =
        context
          ? `${prefix}次に、${placeName(place)}で5を引きます。`
          : `${placeName(place)}で、まず5を引きます。`;

      pushHintMove(
        steps,
        state,
        -5 * place,
        place,
        firstFiveSubtractText
      );

      const rest =
        amount - 5;

      if (rest > 0) {
        pushHintMove(
          steps,
          state,
          -rest * place,
          place,
          `${placeName(place)}で、残りの${rest}を引きます。`
        );
      }

      return;
    }

    // 5をまたぐ引き算。
    // 例: 7-4 → -5、そのあと+1。
    // 説明だけのSTEPを挟まず、最初の珠移動と説明を1つにまとめる。
    if (
      digit >= 5 &&
      amount < 5 &&
      digit - 5 < amount
    ) {
      const complement =
        5 - amount;

      pushHintMove(
        steps,
        state,
        -5 * place,
        place,
        `${digit}から${amount}を引きます。一の珠が${digit - 5}つしかないので、${amount}はそのまま引けません。${amount}の「5の補数」は${complement}です。5を引いて${complement}を足すと${amount}を引けます。まず5を引きます。`
      );

      pushHintMove(
        steps,
        state,
        complement * place,
        place,
        `次に${complement}を足します。5を引いて${complement}を足すと、${amount}を引いたことになります。`
      );

      return;
    }

    pushHintMove(
      steps,
      state,
      -amount * place,
      place,
      `${prefix}${placeName(place)}で${amount}をそのまま引きます。`
    );
  }

  function buildCarryComplementMoves(
    startValue,
    place,
    complement,
    amount
  ) {
    const moves = [];
    let current = startValue;
    const digit =
      hintDigitAt(
        current,
        place
      );

    const placeLabel =
      placeName(place);

    const addMove = (
      nextValue,
      text,
      activePlace = place
    ) => {
      moves.push({
        value: nextValue,
        activePlace,
        text
      });

      current = nextValue;
    };

    if (
      digit >= 5 &&
      complement >= 5
    ) {
      addMove(
        current - 5 * place,
        `${digit}から${complement}を引きます。まず、${placeLabel}で5を引きます。`
      );

      const rest =
        complement - 5;

      if (rest > 0) {
        addMove(
          current - rest * place,
          `あと${rest}を引きます。これで${placeLabel}から${complement}を引けました。`
        );
      }
    } else if (
      digit >= 5 &&
      complement < 5 &&
      digit - 5 < complement
    ) {
      const back =
        5 - complement;

      addMove(
        current - 5 * place,
        `${digit}から${complement}を引きます。一の珠が${digit - 5}つしかないので、${complement}はそのまま引けません。${complement}の「5の補数」は${back}です。5を引いて${back}を足すと${complement}を引けます。まず、${placeLabel}で5を引きます。`
      );

      addMove(
        current + back * place,
        `次に${back}を足します。5を引いて${back}を足すと、${complement}を引いたことになります。`
      );
    } else {
      addMove(
        current - complement * place,
        `${digit}から${complement}を引きます。`
      );
    }

    const upperPlace =
      place * 10;

    addMove(
      current + 10 * place,
      `${placeName(upperPlace)}に1を足しましょう。これは10を1つ足すことです。`,
      upperPlace
    );

    return moves;
  }

  function addDigitWithCarryHint(
    steps,
    state,
    place,
    amount,
    carryContext = false
  ) {
    if (amount <= 0) {
      return;
    }

    const digit =
      hintDigitAt(
        state.value,
        place
      );

    if (
      digit + amount <= 9
    ) {
      addWithinDigitHint(
        steps,
        state,
        place,
        amount,
        carryContext
          ? "くり上がりです。"
          : ""
      );
      return;
    }

    const complement =
      10 - amount;

    const startValue =
      state.value;

    const localSum =
      digit + amount;

    const autoMoves =
      buildCarryComplementMoves(
        startValue,
        place,
        complement,
        amount
      );

    const questionText =
      `${digit}に${amount}を足すと${localSum}になります。\n答えが10をこえるので、${amount}は「10から補数を引く」と考えます。\n${amount}を足すときに使う「10の補数」はいくつですか？`;

    const narrationText =
      `${digit}に${amount}を足すと${localSum}になります。答えが10をこえるので、${amount}は、10から補数を引くと考えます。${amount}を足すときに使う、10の補数はいくつですか？`;

    const voicePromptLead =
      `${digit}に${amount}を足すと${localSum}になります。答えが10をこえるので、${amount}は、10から補数を引くと考えます。${amount}を足すときに使う、`;

    const voicePromptTail =
      `10の補数はいくつですか？ マイクで答えてね。`;

    steps.push({
      value: state.value,
      activePlace: place,
      text: questionText,
      narrationText,
      voicePromptLead,
      voicePromptTail,
      kind: "carry-complement-question",
      expectedAnswer: complement,
      complement,
      amount,
      localDigit: digit,
      startValue,
      finalValue:
        startValue +
        amount * place,
      autoMoves,
      highlightUsed: true,
      resolved: false,
      animationDone: false,
      moveCursor: 0,
      displayValue: state.value,
      displayActivePlace: place,
      lastMoveText: "",
      lastDisplayText: ""
    });

    // 自動アニメーションで最終的にこの値になる。
    // 後続のヒント生成では完成後の値として扱う。
    state.value =
      startValue +
      amount * place;
  }

  function subtractDigitWithBorrowHint(
    steps,
    state,
    place,
    amount,
    borrowContext = false
  ) {
    if (amount <= 0) {
      return;
    }

    const digit =
      hintDigitAt(
        state.value,
        place
      );

    if (
      digit >= amount
    ) {
      if (borrowContext) {
        pushHintMove(
          steps,
          state,
          -amount * place,
          place,
          `${placeName(place)}から${amount}を引きます。`
        );
      } else {
        subtractWithinDigitHint(
          steps,
          state,
          place,
          amount,
          ""
        );
      }
      return;
    }

    const complement =
      10 - amount;

    steps.push({
      value: state.value,
      activePlace: place,
      text:
        `${placeName(place)}だけでは${amount}を引けません。\n${amount}を引くときに使う「10の補数」はいくつですか？`,
      narrationText:
        `${placeName(place)}だけでは${amount}を引けません。${amount}を引くときに使う、10の補数はいくつですか？`,
      voicePromptLead:
        `${placeName(place)}だけでは${amount}を引けません。${amount}を引くときに使う、`,
      voicePromptTail:
        `10の補数はいくつですか？ マイクで答えてね。`,
      kind: "borrow-complement-question",
      expectedAnswer: complement,
      amount,
      place,
      highlightUsed: true,
      resolved: false,
      resolvedText:
        `正解。${amount}を引くときに使う「10の補数」は${complement}です。${amount}を引くときは、まず${placeName(place * 10)}から1を引いて、そのあと${placeName(place)}に${complement}を足します。まず、10の位を動かしましょう。`
    });

    // 先に1つ上の位から1を引く。これが繰り下がり。
    subtractDigitWithBorrowHint(
      steps,
      state,
      place * 10,
      1,
      true
    );

    addWithinDigitHint(
      steps,
      state,
      place,
      complement,
      `${amount}の「10の補数」${complement}を使って、`
    );
  }

  function buildAddSubHintSteps(q) {
    const steps = [
      {
        value: q.a,
        activePlace: null,
        text:
          `まず、${q.a}をそろばんに置きます。使っている珠が薄い黄色に光ります。`,
        narrationText:
          `まず、${q.a}をそろばんに置きます。`,
        highlightAllUsed: true
      },
      {
        value: q.a,
        activePlace: null,
        text:
          q.op === "＋"
            ? `${q.a}に${q.b}を足していきます。`
            : `${q.a}から${q.b}を引いていきます。`,
        narrationText:
          q.op === "＋"
            ? `${q.a}に${q.b}を足していきます。`
            : `${q.a}から${q.b}を引いていきます。`
      }
    ];

    const state = {
      value: q.a
    };

    const parts =
      decomposeByPlace(
        q.b
      );

    parts.forEach((part) => {
      if (q.op === "＋") {
        const digit =
          hintDigitAt(
            state.value,
            part.place
          );

        if (
          digit + part.digit > 9
        ) {
          addDigitWithCarryHint(
            steps,
            state,
            part.place,
            part.digit
          );
        } else {
          pushHintExplain(
            steps,
            state,
            part.place,
            `${placeName(part.place)}に${part.digit}をそのまま足します。`
          );

          addDigitWithCarryHint(
            steps,
            state,
            part.place,
            part.digit
          );
        }
      } else {
        pushHintExplain(
          steps,
          state,
          part.place,
          `${placeName(part.place)}から${part.digit}を引いていきます。`
        );

        subtractDigitWithBorrowHint(
          steps,
          state,
          part.place,
          part.digit
        );
      }
    });

    steps.push({
      value: q.answer,
      activePlace: null,
      text:
        "できました。答えはいくつになっていますか？",
      narrationText:
        "できました。答えはいくつになっていますか？",
      kind: "final-answer-question",
      expectedAnswer: q.answer,
      resolved: false
    });

    return steps;
  }

  function buildMultiTermHintSteps(q) {
    const terms = questionTerms(q);
    const operators = questionOperators(q);
    const steps = [
      {
        value: terms[0],
        activePlace: null,
        text: `まず、${terms[0]}をそろばんに置きます。`,
        narrationText: `まず、${terms[0]}をそろばんに置きます。`,
        highlightAllUsed: true
      }
    ];

    let running = terms[0];

    operators.forEach((op, index) => {
      const amount = terms[index + 1];
      const before = running;
      running = calculate(
        running,
        op,
        amount
      );

      steps.push({
        value: before,
        activePlace: null,
        text: `${before} ${op} ${amount} を計算します。`,
        narrationText: `${before} ${op} ${amount} を計算します。`
      });

      steps.push({
        value: running,
        activePlace: null,
        text:
          op === "＋"
            ? `${amount}を足して、${running}です。`
            : `${amount}を引いて、${running}です。`,
        narrationText:
          op === "＋"
            ? `${amount}を足して、${running}です。`
            : `${amount}を引いて、${running}です。`,
        highlightAllUsed: true
      });
    });

    steps.push({
      value: q.answer,
      activePlace: null,
      text: "できました。答えはいくつになっていますか？",
      narrationText: "できました。答えはいくつになっていますか？",
      kind: "final-answer-question",
      expectedAnswer: q.answer,
      resolved: false
    });

    return steps;
  }

  function buildResultPlacementSteps(q) {
    const answer = Math.max(0, Math.floor(q.answer));
    const parts = decomposeByPlace(answer);

    const steps = [
      {
        value: 0,
        activePlace: null,
        text:
          q.op === "×"
            ? "掛け算では、答えの珠の置き方を位ごとに見てみます。"
            : "割り算では、答えの珠の置き方を位ごとに見てみます。"
      }
    ];

    let current = 0;

    parts.forEach((part) => {
      current += part.amount;

      steps.push({
        value: current,
        activePlace: part.place,
        text:
          `${placeName(part.place)}に ${part.digit} を置きます。`
      });
    });

    steps.push({
      value: answer,
      activePlace: null,
      text:
        "できました。答えはいくつになっていますか？",
      narrationText:
        "できました。答えはいくつになっていますか？",
      kind: "final-answer-question",
      expectedAnswer: answer,
      resolved: false
    });

    return steps;
  }

  function buildHintSteps(q) {
    if (isMultiTermQuestion(q)) {
      return buildMultiTermHintSteps(q);
    }

    if (q.op === "＋" || q.op === "－") {
      return buildAddSubHintSteps(q);
    }

    return buildResultPlacementSteps(q);
  }

  function stopSorobanHintAnimation() {
    hintRunToken += 1;
    hintNarrationToken += 1;
    hintAutoAnimating = false;

    stopHintQuestionRecognition();

    if (sorobanBoard) {
      sorobanBoard.classList.remove(
        "slow-hint-motion"
      );
    }

    if (
      hintNarrationActive &&
      "speechSynthesis" in window
    ) {
      cancelAppSpeech();
    }
  }

  function hideSorobanHint() {
    stopSorobanHintAnimation();

    hintNarrationActive = false;
    hintManualSteps = [];
    hintManualIndex = 0;
    hintAutoAnimating = false;
    stopHintQuestionRecognition();
    setHintVoiceStatus("");
    hideHintAnswerControls();
    refreshBgmVolume();

    abacusHint.classList.remove("show");
    hintStep.textContent = "";
    hintStepCounter.textContent = "";
    sorobanBoard.innerHTML = "";
    hintRods = [];

    // ヒント前から音声回答ONだった場合は、
    // 「ゴワサン」を言い直さず、同じ問題でマイクだけ戻す。
    if (
      voiceAnswerEnabled &&
      !locked &&
      workspace.classList.contains("show") &&
      !results.classList.contains("show") &&
      currentMode
    ) {
      scheduleSilentVoiceRestart(
        420
      );
    }
  }

  function setHintVoiceStatus(
    message = "",
    state = ""
  ) {
    if (!hintVoiceStatus) {
      return;
    }

    hintVoiceStatus.textContent =
      message;

    hintVoiceStatus.classList.toggle(
      "show",
      Boolean(message)
    );

    hintVoiceStatus.classList.remove(
      "listening",
      "correct",
      "wrong"
    );

    if (state) {
      hintVoiceStatus.classList.add(
        state
      );
    }
  }

  function hideHintAnswerControls() {
    if (!hintAnswerControls) {
      return;
    }

    hintAnswerControls.classList.remove(
      "show"
    );

    if (hintMicAnswerBtn) {
      hintMicAnswerBtn.disabled = false;
      hintMicAnswerBtn.style.display = "";
      hintMicAnswerBtn.classList.remove(
        "listening"
      );
      hintMicAnswerBtn.textContent =
        "🎤 声で答える";
    }
  }

  function showHintAnswerControls() {
    if (!hintAnswerControls) {
      return;
    }

    hintAnswerControls.classList.add(
      "show"
    );
  }

  function submitHintComplementAnswer(
    step,
    value,
    source = "button"
  ) {
    const isCarry =
      step?.kind ===
      "carry-complement-question";

    const isBorrow =
      step?.kind ===
      "borrow-complement-question";

    if (
      !step ||
      (!isCarry && !isBorrow) ||
      step.resolved ||
      hintAutoAnimating ||
      hintManualSteps[
        hintManualIndex
      ] !== step
    ) {
      return;
    }

    const numericValue =
      Number(value);

    if (
      step.answerGateOpen ===
        false
    ) {
      step.pendingHintAnswer = {
        value: numericValue,
        source
      };

      setHintVoiceStatus(
        "解説を最後まで聞いてから判定します。",
        "listening"
      );
      return;
    }

    const hintQuestionOk =
      numericValue ===
      step.expectedAnswer;

    learningTick();
    const cq=mainStampAttempt?.questions[String(index)];
    cmResponse(mainStampAttempt,cq,hintQuestionOk,numericValue,"hint:"+hintManualIndex,source==="speech"?"speech":"button","answered",step.expectedAnswer);
    markHintQuestionResult(
      index,
      hintQuestionOk
    );

    if (
      hintQuestionOk
    ) {
      step.resolved = true;

      setHintVoiceStatus("");
      hideHintAnswerControls();
      stopHintQuestionRecognition();

      if (isBorrow) {
        step.displayActivePlace =
          step.place * 10;
        step.highlightUsed = true;

        showSorobanNumber(
          step.value,
          step.displayActivePlace,
          {
            highlightUsed: true
          }
        );

        hintStep.textContent =
          step.resolvedText ||
          `正解。${step.expectedAnswer}です。`;

        hintNextBtn.disabled = false;
        hintNextBtn.textContent =
          "進む →";

        speakHintNarration(
          step.resolvedText ||
          `正解。${step.expectedAnswer}です。`
        );

        return;
      }

      // 繰り上がり側は、正解した画面で最初の珠操作まで実行する。
      step.moveCursor = 0;
      step.animationDone = false;
      step.displayValue =
        step.value;
      step.displayActivePlace =
        step.activePlace;
      step.lastMoveText = "";

      const correctLead =
        `正解。${step.amount}を足すときに使う「10の補数」は${step.expectedAnswer}です。`;

      playHintCarryAnimation(
        step,
        correctLead
      );

      return;
    }

    setHintVoiceStatus(
      isBorrow
        ? `ちがいます。${step.amount}を引くときに使う「10の補数」を考えてみよう。`
        : `ちがいます。${step.amount}を足すときに使う「10の補数」を考えてみよう。`,
      "wrong"
    );

    showHintAnswerControls();
  }

  
  function clearHintQuestionRetryTimer() {
    if (!hintQuestionRetryTimer) {
      return;
    }

    clearTimeout(
      hintQuestionRetryTimer
    );

    hintQuestionRetryTimer = null;
  }

  function stopHintQuestionRecognition() {
    clearHintQuestionRetryTimer();
    hintQuestionListening = false;
    hintQuestionListeningStartedAt = 0;
    hintQuestionSpeechDetected = false;

    if (
      hintQuestionRecognition
    ) {
      try {
        hintQuestionRecognition.onend =
          null;
        hintQuestionRecognition.stop();
      } catch (error) {}
    }

    hintQuestionRecognition = null;
    refreshBgmVolume();
  }

  function speakHintNarration(
    message,
    onDone = null
  ) {
    if (
      !hintNarrationActive ||
      !message
    ) {
      if (onDone) {
        onDone();
      }
      return;
    }

    if (
      !("speechSynthesis" in window) ||
      typeof SpeechSynthesisUtterance ===
        "undefined"
    ) {
      if (onDone) {
        onDone();
      }
      return;
    }

    cancelAppSpeech();

    const narrationToken =
      ++hintNarrationToken;

    let finished = false;

    const done = () => {
      if (
        finished ||
        narrationToken !==
          hintNarrationToken
      ) {
        return;
      }

      finished = true;

      if (onDone) {
        onDone();
      }
    };

    const speakNow = (voice) => {
      if (
        narrationToken !==
          hintNarrationToken ||
        !hintNarrationActive
      ) {
        return;
      }

      const utterance =
        new SpeechSynthesisUtterance(
          message
        );

      utterance.lang = "ja-JP";
      utterance.rate = 0.72;
      utterance.pitch = 1.02;
      utterance.volume = appMasterVolume;

      if (voice) {
        utterance.voice = voice;
      }

      utterance.onend = done;
      utterance.onerror = done;

      try {
        window.speechSynthesis.resume();
      } catch (error) {}

      speakWithAppVolume(
        utterance
      );
    };

    // Android Chrome では voices の準備が遅れることがあるため、
    // 日本語音声が準備できてから珠ヒントを読み上げる。
    waitForJapaneseVoice(
      1400
    ).then((voice) => {
      speakNow(voice);
    }).catch(() => {
      speakNow(null);
    });
  }

  // 珠ヒントは回答が先に入っても、解説を最後まで読み上げてから判定する。


  function scheduleHintQuestionRetry(
    step,
    delay = 500
  ) {
    clearHintQuestionRetryTimer();

    hintQuestionRetryTimer =
      setTimeout(() => {
        if (
          abacusHint.classList.contains(
            "show"
          ) &&
          hintManualSteps[
            hintManualIndex
          ] === step &&
          !step.resolved &&
          !hintAutoAnimating &&
          (
            step.kind === "carry-complement-question" ||
            step.kind === "borrow-complement-question" ||
            step.kind === "final-answer-question"
          )
        ) {
          startHintQuestionRecognition(
            step
          );
        }
      }, delay);
  }

  function startHintQuestionRecognition(
    step,
    onReady = null
  ) {
    const isComplement =
      step?.kind ===
        "carry-complement-question" ||
      step?.kind ===
        "borrow-complement-question";

    const isFinalAnswer =
      step?.kind ===
      "final-answer-question";

    if (
      !step ||
      (!isComplement && !isFinalAnswer) ||
      step.resolved ||
      hintAutoAnimating ||
      hintManualSteps[
        hintManualIndex
      ] !== step
    ) {
      return;
    }

    const Recognition =
      getSpeechRecognitionClass();

    if (!Recognition) {
      setHintVoiceStatus(
        isFinalAnswer
          ? "この端末では音声認識を使えません。手元で答えを入力してね。"
          : "この端末では音声認識を使えません。数字をタップしてね。",
        "wrong"
      );

      if (isComplement) {
        showHintAnswerControls();
      }
      return;
    }

    stopHintQuestionRecognition();

    const recognition =
      new Recognition();
    appDiagnostics.observeRecognition(recognition);

    hintQuestionRecognition =
      recognition;

    recognition.lang =
      "ja-JP";
    recognition.continuous =
      false;
    recognition.interimResults =
      false;
    recognition.maxAlternatives =
      8;

    if (isComplement) {
      try {
        const GrammarList =
          window.SpeechGrammarList ||
          window.webkitSpeechGrammarList;

        if (GrammarList) {
          const grammars =
            new GrammarList();

          grammars.addFromString(
            "#JSGF V1.0; grammar digit; public <digit> = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 一 | 二 | 三 | 四 | 五 | 六 | 七 | 八 | 九;",
            1
          );

          recognition.grammars =
            grammars;
        }
      } catch (error) {}
    }

    recognition.onstart = () => {
      hintQuestionListening =
        true;
      hintQuestionListeningStartedAt =
        Date.now();
      hintQuestionSpeechDetected =
        false;
      refreshBgmVolume();

      if (hintMicAnswerBtn) {
        hintMicAnswerBtn.disabled = true;
        hintMicAnswerBtn.classList.add(
          "listening"
        );
        hintMicAnswerBtn.textContent =
          "🎤 聞いています…";
      }

      // 質問文はhintStepに1回だけ表示する。
      setHintVoiceStatus(
        "🎤 聞いています…",
        "listening"
      );

      if (
        typeof onReady ===
        "function"
      ) {
        const ready =
          onReady;
        onReady = null;

        try {
          ready();
        } catch (error) {}
      }
    };

    recognition.onspeechstart = () => {
      hintQuestionSpeechDetected =
        true;

      // 子どもが話しても珠ヒントの解説は最後まで読み上げる。
      // 回答は保持し、解説が終わってから判定する。
      refreshBgmVolume();

      setHintVoiceStatus(
        "🎤 聞いています…",
        "listening"
      );
    };

    recognition.onspeechend = () => {
      setHintVoiceStatus(
        "🎤 確認中…",
        "listening"
      );
    };

    recognition.onresult = (
      event
    ) => {
      cmLastInput="speech";
      const result =
        event.results?.[0];

      const selected =
        isComplement
          ? selectBestHintSingleDigitSpeech(
              result
            )
          : selectBestNumericSpeech(
              result
            );

      if (!selected) {
        setHintVoiceStatus(
          voiceAnswerEnabled
            ? "数字を聞き取れませんでした。もう一度聞きます。"
            : "数字を聞き取れませんでした。",
          "wrong"
        );
        return;
      }

      if (isFinalAnswer) {
        if (
          step.answerGateOpen ===
            false
        ) {
          step.pendingHintAnswer = {
            value: selected.value,
            source: "voice"
          };
          setHintVoiceStatus(
            "解説を最後まで聞いてから判定します。",
            "listening"
          );
          return;
        }

        if (
          Number(selected.value) ===
          Number(step.expectedAnswer)
        ) {
          step.resolved = true;
          stopHintQuestionRecognition();
          setHintVoiceStatus("");

          answerInput.value =
            String(selected.value);

          hintNarrationActive = false;
          refreshBgmVolume();

          submitAnswer();
        } else {
          setHintVoiceStatus(
            "ちがいます。そろばんを見て、もう一度答えてね。",
            "wrong"
          );
        }
        return;
      }

      submitHintComplementAnswer(
        step,
        selected.value,
        "voice"
      );
    };

    recognition.onerror = (
      event
    ) => {
      if(learningActive)cmEmit(learningActive,"learning_activity",{activity_type:"recognition_failed",substep_id:null,result:null,observation_basis:"speech_api_error:"+String(event?.error||"unknown")},learningActive.questions[String(learningClock?.index)]);
      const code =
        event?.error || "";

      const message =
        code === "not-allowed" ||
        code === "service-not-allowed"
          ? (
              isFinalAnswer
                ? "マイクが許可されていません。手元で答えを入力してね。"
                : "マイクが許可されていません。数字をタップしてね。"
            )
          : voiceAnswerEnabled
            ? "マイクで聞き取れませんでした。もう一度聞きます。"
            : "マイクで聞き取れませんでした。";

      setHintVoiceStatus(
        message,
        "wrong"
      );
    };

    recognition.onend = () => {
      hintQuestionListening =
        false;
      hintQuestionListeningStartedAt =
        0;
      hintQuestionSpeechDetected =
        false;
      hintQuestionRecognition =
        null;
      refreshBgmVolume();

      if (hintMicAnswerBtn) {
        hintMicAnswerBtn.disabled = false;
        hintMicAnswerBtn.classList.remove(
          "listening"
        );
        hintMicAnswerBtn.textContent =
          "🎤 声で答える";
      }

      // マイクモードONなら、未回答の質問は静かに聞き直す。
      if (
        voiceAnswerEnabled &&
        abacusHint.classList.contains(
          "show"
        ) &&
        hintManualSteps[
          hintManualIndex
        ] === step &&
        !step.resolved &&
        !hintAutoAnimating
      ) {
        scheduleHintQuestionRetry(
          step,
          HINT_MIC_RETRY_MS
        );
      }
    };

    // 読み上げが終わったら、子どもが話し始める前にマイクを開く。
    // onstartを待ってから表示を変えると、話し始めの数字を取りこぼすため、
    // start()の直前から「聞いています」にしてBGMも消す。
    hintQuestionListening =
      true;
    hintQuestionSpeechDetected =
      false;
    refreshBgmVolume();

    if (hintMicAnswerBtn) {
      hintMicAnswerBtn.disabled = true;
      hintMicAnswerBtn.classList.add(
        "listening"
      );
      hintMicAnswerBtn.textContent =
        "🎤 聞いています…";
    }

    setHintVoiceStatus(
      "🎤 聞いています…",
      "listening"
    );

    try {
      recognition.start();
    } catch (error) {
      hintQuestionRecognition =
        null;
      hintQuestionListening =
        false;
      hintQuestionListeningStartedAt =
        0;
      hintQuestionSpeechDetected =
        false;
      refreshBgmVolume();

      setHintVoiceStatus(
        isFinalAnswer
          ? "マイクを開始できませんでした。手元で答えを入力してね。"
          : "マイクを開始できませんでした。数字をタップしてね。",
        "wrong"
      );

      if (hintMicAnswerBtn) {
        hintMicAnswerBtn.disabled = false;
        hintMicAnswerBtn.classList.remove(
          "listening"
        );
        hintMicAnswerBtn.textContent =
          "🎤 声で答える";
      }
    }
  }

  function playHintCarryAnimation(
    step,
    leadText = ""
  ) {
    if (
      !step ||
      !Array.isArray(
        step.autoMoves
      ) ||
      !step.autoMoves.length ||
      !step.resolved
    ) {
      return;
    }

    stopHintQuestionRecognition();

    const moveIndex =
      Math.max(
        0,
        Number.isInteger(
          step.moveCursor
        )
          ? step.moveCursor
          : 0
      );

    if (
      moveIndex >=
      step.autoMoves.length
    ) {
      step.animationDone = true;
      hintNextBtn.disabled = false;
      hintNextBtn.textContent =
        hintManualIndex >=
          hintManualSteps.length - 1
          ? "もう一度見る"
          : "進む →";
      return;
    }

    const move =
      step.autoMoves[
        moveIndex
      ];

    hintAutoAnimating = true;
    hintPrevBtn.disabled = true;
    hintNextBtn.disabled = true;
    hintNextBtn.textContent =
      "珠を動かしています…";

    sorobanBoard.classList.add(
      "slow-hint-motion"
    );

    const displayText =
      leadText
        ? `${leadText}\n${move.text}`
        : move.text;

    hintStep.textContent =
      displayText;

    showSorobanNumber(
      move.value,
      move.activePlace,
      {
        highlightChanged: true
      }
    );

    step.displayValue =
      move.value;
    step.displayActivePlace =
      move.activePlace;
    step.lastMoveText =
      move.text;
    step.lastDisplayText =
      displayText;

    speakHintNarration(
      displayText,
      () => {
        // 1回のアニメーションで進む珠操作は1つだけ。
        step.moveCursor =
          moveIndex + 1;

        step.animationDone =
          step.moveCursor >=
          step.autoMoves.length;

        hintAutoAnimating = false;
        sorobanBoard.classList.remove(
          "slow-hint-motion"
        );

        // 最初の珠操作が終わった後も「戻る」を有効にする。
        // 同じcarry step内の1つ前の珠状態へ戻れる。
        hintPrevBtn.disabled =
          false;

        hintNextBtn.disabled = false;
        hintNextBtn.textContent =
          step.animationDone &&
          hintManualIndex >=
            hintManualSteps.length - 1
            ? "もう一度見る"
            : "進む →";

        setHintVoiceStatus("");
      }
    );
  }

  
  function openHintAnswerGate(
    step
  ) {
    if (!step) {
      return;
    }

    step.answerGateOpen = true;

    const pending =
      step.pendingHintAnswer ||
      null;

    step.pendingHintAnswer =
      null;

    if (!pending) {
      return;
    }

    if (
      step.kind ===
        "final-answer-question"
    ) {
      const value =
        Number(pending.value);

      if (
        value ===
        Number(step.expectedAnswer)
      ) {
        step.resolved = true;
        stopHintQuestionRecognition();
        setHintVoiceStatus("");
        answerInput.value =
          String(value);
        hintNarrationActive = false;
        refreshBgmVolume();
        submitAnswer();
      } else {
        setHintVoiceStatus(
          "ちがいます。そろばんを見て、もう一度答えてね。",
          "wrong"
        );
      }
      return;
    }

    submitHintComplementAnswer(
      step,
      pending.value,
      pending.source || "voice"
    );
  }

  function renderManualHintStep(
    stepIndex,
    speak = true
  ) {
    if (
      !hintManualSteps.length ||
      !abacusHint.classList.contains(
        "show"
      )
    ) {
      return;
    }

    stopHintQuestionRecognition();
    hintAutoAnimating = false;
    sorobanBoard.classList.remove(
      "slow-hint-motion"
    );
    setHintVoiceStatus("");

    const safeIndex =
      Math.max(
        0,
        Math.min(
          hintManualSteps.length - 1,
          Number(stepIndex) || 0
        )
      );

    hintManualIndex =
      safeIndex;

    const step =
      hintManualSteps[
        hintManualIndex
      ];

    const displayValue =
      Number.isFinite(
        step.displayValue
      )
        ? step.displayValue
        : step.value;

    const displayActivePlace =
      step.displayActivePlace ??
      step.activePlace;

    showSorobanNumber(
      displayValue,
      displayActivePlace,
      {
        highlightUsed:
          Boolean(
            step.highlightUsed
          ),
        highlightAllUsed:
          Boolean(
            step.highlightAllUsed
          ),
        highlightChanged:
          Boolean(
            step.highlightChanged
          )
      }
    );

    const isCarryQuestion =
      step.kind ===
      "carry-complement-question";

    const isBorrowQuestion =
      step.kind ===
      "borrow-complement-question";

    const isComplementQuestion =
      isCarryQuestion ||
      isBorrowQuestion;

    const isFinalAnswer =
      step.kind ===
      "final-answer-question";

    const hintAnswerInstruction =
      voiceAnswerEnabled
        ? "マイクで答えてね。"
        : "数字をタップしてね。";

    if (
      isFinalAnswer &&
      !step.resolved
    ) {
      hideHintAnswerControls();

      const finalInstruction =
        voiceAnswerEnabled
          ? "マイクで答えてね。"
          : "手元で答えを入力してね。";

      hintStep.textContent =
        `${step.text}\n${finalInstruction}`;

      hintStepCounter.textContent =
        `STEP ${hintManualIndex + 1} / ${hintManualSteps.length}`;

      hintPrevBtn.disabled =
        hintManualIndex <= 0;

      hintNextBtn.disabled =
        true;
      hintNextBtn.textContent =
        voiceAnswerEnabled
          ? "マイクで答えてね"
          : "答えを入力してね";

      const finalNarration =
        `${step.narrationText || step.text} ${finalInstruction}`;

      step.answerGateOpen =
        !(
          speak ||
          voiceAnswerEnabled
        );
      step.pendingHintAnswer =
        null;

      if (
        voiceAnswerEnabled
      ) {
        const startFinalMic =
          () => {
            if (
              hintManualSteps[
                hintManualIndex
              ] !== step ||
              step.resolved ||
              !abacusHint.classList.contains(
                "show"
              )
            ) {
              return;
            }

            startHintQuestionRecognition(
              step,
              () => {
                if (
                  hintManualSteps[
                    hintManualIndex
                  ] !== step ||
                  step.resolved
                ) {
                  return;
                }

                speakHintNarration(
                  "答えはいくつになっていますか？ マイクで答えてね。",
                  () => {
                    openHintAnswerGate(
                      step
                    );
                  }
                );
              }
            );
          };

        if (speak) {
          speakHintNarration(
            "できました。",
            startFinalMic
          );
        } else {
          startFinalMic();
        }
      } else if (speak) {
        speakHintNarration(
          finalNarration,
          () => {
            openHintAnswerGate(
              step
            );
          }
        );
      } else {
        openHintAnswerGate(
          step
        );
      }

      return;
    }

    hintStep.textContent =
      isComplementQuestion &&
      !step.resolved
        ? `${step.text}\n${hintAnswerInstruction}`
        : isBorrowQuestion &&
          step.resolved
          ? step.resolvedText ||
            `正解。${step.expectedAnswer}です。`
          : isCarryQuestion &&
            step.resolved
            ? step.lastDisplayText ||
              step.lastMoveText ||
              `正解。${step.amount}を足すときに使う「10の補数」は${step.expectedAnswer}です。まず、${step.localDigit}から${step.expectedAnswer}を引きます。`
            : step.text;

    hintStepCounter.textContent =
      `STEP ${hintManualIndex + 1} / ${hintManualSteps.length}`;

    hintPrevBtn.disabled =
      hintManualIndex <= 0;

    if (
      isComplementQuestion &&
      !step.resolved
    ) {
      hintNextBtn.disabled =
        true;
      hintNextBtn.textContent =
        "答えてから進む";

      showHintAnswerControls();

      if (hintMicAnswerBtn) {
        hintMicAnswerBtn.style.display =
          voiceAnswerEnabled
            ? ""
            : "none";
      }

      // 質問文の重複を避け、状態だけ短く出す。
      setHintVoiceStatus(
        voiceAnswerEnabled
          ? ""
          : ""
      );

      const questionNarration =
        `${step.narrationText || step.text} ${hintAnswerInstruction}`;

      step.answerGateOpen =
        !(
          speak ||
          voiceAnswerEnabled
        );
      step.pendingHintAnswer =
        null;

      if (
        voiceAnswerEnabled
      ) {
        const startMicAndQuestionTail =
          () => {
            if (
              hintManualSteps[
                hintManualIndex
              ] !== step ||
              step.resolved ||
              hintAutoAnimating ||
              !abacusHint.classList.contains(
                "show"
              )
            ) {
              return;
            }

            startHintQuestionRecognition(
              step,
              () => {
                if (
                  hintManualSteps[
                    hintManualIndex
                  ] !== step ||
                  step.resolved ||
                  !abacusHint.classList.contains(
                    "show"
                  )
                ) {
                  return;
                }

                speakHintNarration(
                  step.voicePromptTail ||
                  "10の補数はいくつですか？ マイクで答えてね。",
                  () => {
                    openHintAnswerGate(
                      step
                    );
                  }
                );
              }
            );
          };

        if (
          speak &&
          step.voicePromptLead
        ) {
          speakHintNarration(
            step.voicePromptLead,
            startMicAndQuestionTail
          );
        } else {
          startMicAndQuestionTail();
        }
      } else if (speak) {
        speakHintNarration(
          questionNarration,
          () => {
            openHintAnswerGate(
              step
            );
          }
        );
      } else {
        openHintAnswerGate(
          step
        );
      }

      return;
    }

    hideHintAnswerControls();
    setHintVoiceStatus("");

    hintNextBtn.disabled = false;

    hintNextBtn.textContent =
      hintManualIndex >=
        hintManualSteps.length - 1
        ? "もう一度見る"
        : "進む →";

    if (speak) {
      if (
        isBorrowQuestion &&
        step.resolved
      ) {
        speakHintNarration(
          step.resolvedText ||
          `正解。${step.expectedAnswer}です。`
        );
      } else if (
        isCarryQuestion &&
        step.resolved
      ) {
        const resolvedNarration =
          step.lastDisplayText ||
          step.lastMoveText ||
          `正解。${step.amount}を足すときに使う10の補数は${step.expectedAnswer}です。まず、${step.localDigit}から${step.expectedAnswer}を引きます。`;
        speakHintNarration(
          resolvedNarration
        );
      } else {
        speakHintNarration(
          step.narrationText ||
            step.text
        );
      }
    }
  }

  
  function restoreCarryMoveState(
    step,
    cursor,
    speak = true
  ) {
    if (
      !step ||
      step.kind !==
        "carry-complement-question"
    ) {
      return;
    }

    const safeCursor =
      Math.max(
        0,
        Math.min(
          step.autoMoves.length,
          Number(cursor) || 0
        )
      );

    step.moveCursor =
      safeCursor;

    step.animationDone =
      safeCursor >=
      step.autoMoves.length;

    let textToShow = "";
    let value =
      step.value;
    let activePlace =
      step.activePlace;

    if (safeCursor > 0) {
      const move =
        step.autoMoves[
          safeCursor - 1
        ];

      value =
        move.value;
      activePlace =
        move.activePlace;
      step.lastMoveText =
        move.text;

      textToShow =
        move.text;
    } else {
      step.lastMoveText = "";

      textToShow =
        `正解。${step.amount}を足すときに使う「10の補数」は${step.expectedAnswer}です。まず、${step.localDigit}から${step.expectedAnswer}を引きます。`;
    }

    step.displayValue =
      value;
    step.displayActivePlace =
      activePlace;
    step.lastDisplayText =
      textToShow;

    showSorobanNumber(
      value,
      activePlace,
      {
        highlightChanged:
          safeCursor > 0
      }
    );

    hintStep.textContent =
      textToShow;

    hideHintAnswerControls();
    setHintVoiceStatus("");

    hintPrevBtn.disabled =
      safeCursor === 0 &&
      hintManualIndex <= 0;

    hintNextBtn.disabled =
      false;

    hintNextBtn.textContent =
      "進む →";

    if (
      speak &&
      textToShow
    ) {
      speakHintNarration(
        textToShow
      );
    }
  }

  function moveManualHint(
    direction
  ) {
    if (
      !hintManualSteps.length ||
      hintAutoAnimating
    ) {
      return;
    }

    const currentStep =
      hintManualSteps[
        hintManualIndex
      ];

    // Carry step内では、「戻る」も珠操作1回単位で戻す。
    if (
      direction < 0 &&
      currentStep?.kind ===
        "carry-complement-question" &&
      currentStep.resolved &&
      Number(currentStep.moveCursor) > 0
    ) {
      restoreCarryMoveState(
        currentStep,
        currentStep.moveCursor - 1,
        true
      );
      return;
    }

    if (
      direction > 0 &&
      currentStep?.kind ===
        "final-answer-question" &&
      !currentStep.resolved
    ) {
      return;
    }

    if (
      direction > 0 &&
      currentStep?.kind ===
        "carry-complement-question"
    ) {
      if (
        !currentStep.resolved
      ) {
        return;
      }

      if (
        !currentStep.animationDone
      ) {
        playHintCarryAnimation(
          currentStep
        );
        return;
      }
    }

    const nextIndex =
      hintManualIndex +
      direction;

    if (
      direction > 0 &&
      nextIndex >=
        hintManualSteps.length
    ) {
      hintManualSteps.forEach(
        (step) => {
          if (
            step?.kind !==
              "carry-complement-question" &&
            step?.kind !==
              "borrow-complement-question"
          ) {
            return;
          }

          step.resolved = false;

          if (
            step.kind ===
            "carry-complement-question"
          ) {
            step.animationDone = false;
            step.moveCursor = 0;
            step.displayValue =
              step.value;
            step.displayActivePlace =
              step.activePlace;
            step.lastMoveText = "";
            step.lastDisplayText = "";
          }
        }
      );

      renderManualHintStep(
        0,
        true
      );
      return;
    }

    if (
      nextIndex < 0 ||
      nextIndex >=
        hintManualSteps.length
    ) {
      return;
    }

    renderManualHintStep(
      nextIndex,
      true
    );
  }

  
  function runSorobanHint() {
    if (sessionVideoActive) {
      feedback.textContent =
        "撮影中は珠ヒントを使わず、終了後の解説・補習で復習します。";
      feedback.className =
        "feedback";
      return;
    }

    if (
      index >= sessionTotalQuestions ||
      !questions[index]
    ) {
      return;
    }

    const q =
      questions[index];

    learningHint(mainStampAttempt,index);
    markQuestionHintUsed(
      index
    );

    recordVideoHintUse(
      index
    );

    const steps =
      buildHintSteps(q);

    const maxValue =
      Math.max(
        ...questionTerms(q).map(
          (value) => Math.abs(value)
        ),
        Math.abs(q.answer),
        ...steps.map(
          (step) =>
            Math.abs(step.value)
        )
      );

    const digitCount =
      Math.max(
        1,
        String(
          Math.floor(maxValue)
        ).length
      );

    stopSorobanHintAnimation();

    // ヒントの音声と回答用マイクを同時に動かさない。
    hintNarrationActive = true;
    clearVoiceRestartTimer();
    stopVoiceRecognition();
    refreshBgmVolume();

    buildSorobanBoard(
      digitCount
    );

    abacusHint.classList.add(
      "show"
    );

    hintManualSteps =
      steps;

    hintManualIndex = 0;

    // 開いた直後はSTEP1で停止。
    // 以後は「進む」「戻る」を押した時だけ珠が変わる。
    renderManualHintStep(
      0,
      true
    );
  }

  function getTargetBgmVolume() {
    if (
      voiceSpeechDetected ||
      anzanSpeechDetected ||
      kukuSpeechDetected ||
      hintQuestionListening
    ) {
      return BGM_VOLUME_LISTENING;
    }

    if (kukuPromptSpeaking) {
      return BGM_VOLUME_APP_SPEECH;
    }

    if (
      voiceCalloutRunning ||
      voicePauseForFeedback ||
      hintNarrationActive
    ) {
      return BGM_VOLUME_APP_SPEECH;
    }

    // 九九名人もチャレンジと同じ通常音量を使う。
    if (
      kukuView &&
      kukuView.classList.contains("show") &&
      kukuGameView &&
      !kukuGameView.classList.contains("hidden")
    ) {
      return BGM_VOLUME_NORMAL;
    }

    return BGM_VOLUME_NORMAL;
  }

  function refreshBgmVolume() {
    bgmEngine.setVolume(
      getTargetBgmVolume()
    );
  }

  function startBgmKeepAlive() {
    if (bgmKeepAliveTimer) {
      return;
    }

    bgmKeepAliveTimer =
      setInterval(() => {
        if (
          !bgmOn || !(
            (voiceAnswerEnabled && workspace.classList.contains("show") && !results.classList.contains("show")) ||
            (kukuVoiceEnabled && kukuView.classList.contains("show") && !kukuGameView.classList.contains("hidden"))
          )
        ) {
          return;
        }

        // 音声認識中にブラウザがAudioContextを
        // suspendしていないか定期的に確認する。
        bgmEngine.keepAlive();

        if (
          currentBgm &&
          !bgmEngine.hasActiveSource()
        ) {
          bgmEngine.play(
            currentBgm,
            true
          );
        }

        refreshBgmVolume();
      }, 400);
  }

  function stopBgmKeepAlive() {
    if (!bgmKeepAliveTimer) {
      return;
    }

    clearInterval(
      bgmKeepAliveTimer
    );

    bgmKeepAliveTimer = null;
  }

  function chooseRandomTrack(tracks) {
    return tracks[
      Math.floor(
        Math.random() * tracks.length
      )
    ];
  }

  function desiredBgmName(streak) {
    let groupKey;
    let tracks;

    if (streak <= 2) {
      groupKey = "1-3";
      tracks = [
        "1.mp3",
        "2.mp3",
        "3.mp3"
      ];
    } else if (streak <= 5) {
      groupKey = "4-6";
      tracks = [
        "4.mp3",
        "5.mp3",
        "6.mp3"
      ];
    } else if (streak <= 9) {
      groupKey = "7-9";
      tracks = [
        "7.mp3",
        "8.mp3",
        "9.mp3"
      ];
    } else {
      groupKey = "10";
      tracks = [
        "10-1.mp3",
        "10-2.mp3",
        "10-3.mp3"
      ];
    }

    // 同じ連続正解帯の中では、選んだ曲をそのまま流す。
    if (
      currentBgmGroupKey === groupKey &&
      currentBgm &&
      tracks.includes(currentBgm)
    ) {
      return currentBgm;
    }

    // 次の帯に入った時だけ、その帯からランダム選択。
    currentBgmGroupKey = groupKey;

    return chooseRandomTrack(tracks);
  }

  function updateBgmButton() {
    bgmBtn.textContent =
      bgmOn
        ? "♪ BGM ON"
        : "♪ BGM OFF";
  }

  function playBgmForStreak(
    streak,
    force = false
  ) {
    const name =
      desiredBgmName(streak);

    currentBgm = name;

    bgmName.textContent =
      `BGM：${name}`;

    if (!bgmOn) {
      return;
    }

    // ここではマイク状態にかかわらず
    // BGM再生ノードを継続する。
    bgmEngine.setVolume(
      getTargetBgmVolume(),
      0.08
    );

    bgmEngine
      .play(name, force)
      .then((ok) => {
        if (!ok) {
          bgmName.textContent =
            `BGM：${name}（再生できません）`;
          return;
        }

        refreshBgmVolume();
      })
      .catch(() => {
        bgmName.textContent =
          `BGM：${name}（再生できません）`;
      });
  }

  function stopBgm() {
    stopBgmKeepAlive();
    bgmEngine.stop();
  }

  function toggleBgm() {
    bgmOn = !bgmOn;
    saveBooleanSetting(
      BGM_SETTING_KEY,
      bgmOn
    );
    updateBgmButton();
    updateSettingsUi();

    if (
      bgmOn &&
      workspace.classList.contains("show") &&
      !results.classList.contains("show")
    ) {
      // BGMボタンはユーザー操作なので、
      // このイベント内でAudioContextを起動する。
      bgmEngine.ensureContext();

      playBgmForStreak(
        correctStreak,
        true
      );

      if (voiceAnswerEnabled) {
        startBgmKeepAlive();
      }
    } else {
      stopBgm();
    }
  }


  function getSpeechRecognitionClass() {
    return (
      window.SpeechRecognition ||
      window.webkitSpeechRecognition ||
      null
    );
  }

  function japaneseDigitValue(char) {
    const values = {
      "〇": 0,
      "零": 0,
      "一": 1,
      "二": 2,
      "三": 3,
      "四": 4,
      "五": 5,
      "六": 6,
      "七": 7,
      "八": 8,
      "九": 9
    };

    if (
      Object.prototype.hasOwnProperty
        .call(values, char)
    ) {
      return values[char];
    }

    return null;
  }

  function japaneseIntegerToNumber(input) {
    const original =
      String(input || "");

    const compact =
      original
        .replace(
          /[,\s、。,.]/g,
          ""
        )
        .replace(
          /マイナス|minus/gi,
          "-"
        );

    if (!compact) {
      return null;
    }

    // 「15」のように数字で認識された場合。
    const direct =
      compact.match(/-?\d+/);

    if (direct) {
      const value =
        Number(direct[0]);

      return Number.isFinite(value)
        ? value
        : null;
    }

    // ひらがな認識も漢数字へ寄せる。
    const normalized =
      compact
        .replace(/いち/g, "一")
        .replace(/に/g, "二")
        .replace(/さん|サン|山|酸|産|参|算/g, "三")
        .replace(/よん|し/g, "四")
        .replace(/ご/g, "五")
        .replace(/ろく|ロク|録|禄|ろっく|ロック/g, "六")
        .replace(/なな|しち/g, "七")
        .replace(/はち/g, "八")
        .replace(/きゅう|きゅー|急|球|旧|級|く/g, "九")
        .replace(/れい|ぜろ/g, "零")
        .replace(/じゅう/g, "十")
        .replace(/ひゃく/g, "百")
        .replace(/せん/g, "千")
        .replace(/まん/g, "万");

    if (
      !/[一二三四五六七八九〇零十百千万]/
        .test(normalized)
    ) {
      return null;
    }

    let total = 0;
    let section = 0;
    let number = 0;

    const negative =
      normalized.startsWith("-");

    const chars =
      normalized
        .replace("-", "");

    for (const char of chars) {
      const digit =
        japaneseDigitValue(char);

      if (digit !== null) {
        number = digit;
        continue;
      }

      if (
        char === "十" ||
        char === "百" ||
        char === "千"
      ) {
        const unit =
          char === "十"
            ? 10
            : char === "百"
              ? 100
              : 1000;

        section +=
          (number || 1) * unit;

        number = 0;
        continue;
      }

      if (char === "万") {
        section += number;

        total +=
          (section || 1) *
          10000;

        section = 0;
        number = 0;
      }
    }

    const value =
      total +
      section +
      number;

    return negative
      ? -value
      : value;
  }

  function normalizeNumericSpeechText(
    input
  ) {
    return String(
      input || ""
    )
      .toLowerCase()
      .replace(
        /[,\s、。,.！!？?]/g,
        ""
      )
      .replace(
        /答えは|答え|こたえは|こたえ|です|だよ|だね|だ|かな|えっと|えーと|ええと|えー|うーん|はい/g,
        ""
      )
      .replace(
        /マイナス|minus/g,
        "-"
      )
      .replace(/いち/g, "一")
      .replace(/に/g, "二")
      .replace(/さん|サン|山|酸|産|参|算/g, "三")
      .replace(/よん|し/g, "四")
      .replace(/ご/g, "五")
      .replace(/ろく|ロク|録|禄|ろっく|ロック/g, "六")
      .replace(/なな|しち/g, "七")
      .replace(/はち/g, "八")
      .replace(/きゅう|きゅー|急|球|旧|級|く/g, "九")
      .replace(/れい|ぜろ/g, "零")
      .replace(/じゅう/g, "十")
      .replace(/ひゃく/g, "百")
      .replace(/せん/g, "千")
      .replace(/まん/g, "万");
  }

  function isLikelyNumericSpeech(
    input
  ) {
    const normalized =
      normalizeNumericSpeechText(
        input
      );

    if (!normalized) {
      return false;
    }

    // 数字・漢数字以外の言葉が残っている候補は、
    // BGMや周囲の会話の可能性が高いので採用しない。
    return (
      /^-?\d+$/.test(
        normalized
      ) ||
      /^-?[一二三四五六七八九〇零十百千万]+$/.test(
        normalized
      )
    );
  }

  function selectBestNumericSpeech(
    result
  ) {
    if (!result) {
      return null;
    }

    let best = null;

    for (
      let i = 0;
      i < result.length;
      i += 1
    ) {
      const alternative =
        result[i];

      const transcript =
        String(
          alternative?.transcript || ""
        ).trim();

      if (
        !transcript ||
        !isLikelyNumericSpeech(
          transcript
        )
      ) {
        continue;
      }

      const value =
        japaneseIntegerToNumber(
          transcript
        );

      if (
        value === null ||
        !Number.isInteger(value) ||
        value < 0
      ) {
        continue;
      }

      const rawConfidence =
        Number(
          alternative?.confidence
        );

      const confidence =
        Number.isFinite(
          rawConfidence
        )
          ? rawConfidence
          : 0;

      // ブラウザがconfidenceを返している場合、
      // 極端に低い数字候補はBGMや環境音の誤認識として捨てる。
      if (
        confidence > 0 &&
        confidence < 0.22
      ) {
        continue;
      }

      const normalized =
        normalizeNumericSpeechText(
          transcript
        );

      const digitOnlyBonus =
        /^-?\d+$/.test(
          normalized
        )
          ? 0.15
          : 0;

      const score =
        confidence +
        digitOnlyBonus -
        Math.min(
          0.12,
          transcript.length *
            0.002
        );

      if (
        !best ||
        score > best.score
      ) {
        best = {
          value,
          transcript,
          confidence,
          score
        };
      }
    }

    return best;
  }


  function selectBestHintSingleDigitSpeech(
    result
  ) {
    if (!result) {
      return null;
    }

    let best = null;

    for (
      let i = 0;
      i < result.length;
      i += 1
    ) {
      const alternative =
        result[i];

      const transcript =
        String(
          alternative?.transcript || ""
        ).trim();

      if (!transcript) {
        continue;
      }

      const normalized =
        normalizeNumericSpeechText(
          transcript
        );

      if (
        !(
          /^[1-9]$/.test(normalized) ||
          /^[一二三四五六七八九]$/.test(normalized)
        )
      ) {
        continue;
      }

      const value =
        japaneseIntegerToNumber(
          transcript
        );

      if (
        !Number.isInteger(value) ||
        value < 1 ||
        value > 9
      ) {
        continue;
      }

      const rawConfidence =
        Number(
          alternative?.confidence
        );

      const confidence =
        Number.isFinite(
          rawConfidence
        )
          ? rawConfidence
          : 0;

      const directDigitBonus =
        /^[1-9]$/.test(normalized)
          ? 0.24
          : 0.18;

      const score =
        confidence +
        directDigitBonus -
        Math.min(
          0.08,
          transcript.length *
            0.002
        );

      if (
        !best ||
        score > best.score
      ) {
        best = {
          value,
          transcript,
          confidence,
          score
        };
      }
    }

    return best;
  }

  function updateVoiceUi(
    message = null
  ) {
    const supported =
      Boolean(
        getSpeechRecognitionClass()
      );

    if (!supported) {
      voiceBtn.disabled = true;
      voiceBtn.textContent =
        "🎤 音声回答 非対応";

      voiceStatus.textContent =
        "このブラウザでは音声回答を利用できません。";

      voiceStatus.classList.remove(
        "listening"
      );

      return;
    }

    voiceBtn.disabled = false;

    voiceBtn.classList.toggle(
      "on",
      voiceAnswerEnabled
    );

    voiceBtn.textContent =
      voiceAnswerEnabled
        ? "🎤 音声回答 ON"
        : "🎤 音声回答 OFF";

    voiceStatus.textContent =
      message ||
      (
        voiceAnswerEnabled
          ? "音声回答：数字を話してください"
          : "音声回答：OFF"
      );

    voiceStatus.classList.toggle(
      "listening",
      voiceAnswerEnabled &&
      voiceRecognitionRunning &&
      !voicePauseForFeedback
    );
  }

  function clearVoiceRestartTimer() {
    if (!voiceRestartTimer) {
      return;
    }

    clearTimeout(
      voiceRestartTimer
    );

    voiceRestartTimer = null;
  }

  function stopVoiceRecognition() {
    clearVoiceRestartTimer();

    if (!voiceRecognition) {
      voiceRecognitionRunning = false;
      refreshBgmVolume();
      return;
    }

    if (voiceRecognitionRunning) {
      try {
        voiceRecognition.stop();
      } catch (error) {}
    }
  }

  function scheduleVoiceRestart(
    delay = 280
  ) {
    if (
      !voiceAnswerEnabled ||
      voicePauseForFeedback ||
      hintNarrationActive ||
      locked ||
      !workspace.classList.contains("show") ||
      results.classList.contains("show") ||
      abacusHint.classList.contains("show")
    ) {
      return;
    }

    clearVoiceRestartTimer();

    voiceRestartTimer =
      setTimeout(() => {
        if (
          gowasanSpokenForIndex ===
          index
        ) {
          startMicrophoneRecognition();
          return;
        }

        startVoiceRecognition();
      }, delay);
  }

  function scheduleSilentVoiceRestart(
    delay = 320
  ) {
    if (
      !voiceAnswerEnabled ||
      voicePauseForFeedback ||
      voiceCalloutRunning ||
      hintNarrationActive ||
      locked ||
      !workspace.classList.contains("show") ||
      results.classList.contains("show") ||
      abacusHint.classList.contains("show")
    ) {
      return;
    }

    clearVoiceRestartTimer();

    voiceRestartTimer =
      setTimeout(() => {
        startMicrophoneRecognition();
      }, delay);
  }

  function handleRecognizedSpeech(
    event
  ) {
    if (
      locked ||
      !voiceAnswerEnabled ||
      voicePauseForFeedback ||
      voiceCalloutRunning
    ) {
      return;
    }

    const result =
      event.results?.[0];

    if (!result) {
      return;
    }

    // 問題はマイクonstart後に初めて表示されるため、
    // 450ms未満で返る認識結果は子どもの回答とは考えにくい。
    // 直前のBGM・ゴワサンの残響として捨てる。
    if (
      voiceListeningStartedAt > 0 &&
      Date.now() -
        voiceListeningStartedAt <
        MIC_RESULT_GUARD_MS
    ) {
      updateVoiceUi(
        "音声回答：数字を話してください"
      );
      return;
    }

    const selected =
      selectBestNumericSpeech(
        result
      );

    if (!selected) {
      const firstText =
        String(
          result[0]?.transcript || ""
        );

      updateVoiceUi(
        firstText
          ? "音声回答：数字だけを、もう一度話してください"
          : "音声回答：もう一度話してください"
      );
      return;
    }

    answerInput.value =
      String(
        selected.value
      );

    // この認識結果は回答として採用する。
    // stop()後のonendが、回答確定前にマイクを再起動しないようにする。
    voicePauseForFeedback = true;

    updateVoiceUi(
      `音声回答：「${selected.transcript}」→ ${selected.value}`
    );

    stopVoiceRecognition();

    setTimeout(() => {
      if (!locked) {
        submitAnswer();
      }
    }, 160);
  }

  function createVoiceRecognition() {
    const Recognition =
      getSpeechRecognitionClass();

    if (!Recognition) {
      return null;
    }

    const recognition =
      new Recognition();
    appDiagnostics.observeRecognition(recognition);

    recognition.lang = "ja-JP";
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.maxAlternatives = 5;

    recognition.onstart = () => {
      voiceRecognitionRunning = true;
      voiceListeningStartedAt =
        Date.now();
      voiceSpeechDetected = false;

      // マイクがONでも、考えている間のBGMは通常音量。
      refreshBgmVolume();
      bgmEngine.ensureRunning();
      startBgmKeepAlive();

      updateVoiceUi(
        "音声回答：数字を話してください"
      );

      // ① ゴワサン終了
      // ② マイクの onstart を確認
      // ③ ここで初めて問題を生成・表示する
      renderQuestion(true);
    };

    recognition.onspeechstart = () => {
      // ブラウザが人の発話を検知した瞬間だけBGMを消す。
      voiceSpeechDetected = true;
      refreshBgmVolume();

      updateVoiceUi(
        "音声回答：聞いています…"
      );
    };

    recognition.onspeechend = () => {
      // 結果確定まではBGMを戻さず、語尾をBGMで汚さない。
      updateVoiceUi(
        "音声回答：確認中…"
      );
    };

    recognition.onresult =
      handleRecognizedSpeech;

    recognition.onend = () => {
      voiceRecognitionRunning = false;
      voiceListeningStartedAt = 0;
      voiceSpeechDetected = false;

      refreshBgmVolume();
      bgmEngine.ensureRunning();

      if (
        voiceAnswerEnabled &&
        !voicePauseForFeedback &&
        !voiceCalloutRunning &&
        !locked &&
        workspace.classList.contains("show") &&
        !results.classList.contains("show") &&
        !abacusHint.classList.contains("show")
      ) {
        // 無音タイムアウトでは「ゴワサン！」を言い直さない。
        // 同じ問題を表示したまま、マイクだけ静かに再開する。
        scheduleSilentVoiceRestart(
          320
        );
      } else {
        updateVoiceUi();
      }
    };

    recognition.onerror = (
      event
    ) => {
      if(learningActive)cmEmit(learningActive,"learning_activity",{activity_type:"recognition_failed",substep_id:null,result:null,observation_basis:"speech_api_error:"+String(event?.error||"unknown")},learningActive.questions[String(learningClock?.index)]);
      voiceRecognitionRunning = false;
      voiceListeningStartedAt = 0;
      voiceSpeechDetected = false;

      refreshBgmVolume();
      bgmEngine.ensureRunning();

      if (
        event.error ===
        "not-allowed"
      ) {
        voiceAnswerEnabled = false;
        voiceCalloutRunning = false;
        stopBgmKeepAlive();

        updateVoiceUi(
          "マイクが許可されていません。ブラウザでマイクを許可してください。"
        );
        return;
      }

      if (
        event.error === "no-speech" ||
        event.error === "aborted"
      ) {
        if (
          voiceAnswerEnabled &&
          !voicePauseForFeedback &&
          !voiceCalloutRunning &&
          !locked
        ) {
          scheduleSilentVoiceRestart(
            380
          );
        }
        return;
      }

      updateVoiceUi(
        `音声回答：${event.error}`
      );

      if (
        voiceAnswerEnabled &&
        !voicePauseForFeedback &&
        !voiceCalloutRunning &&
        !locked
      ) {
        scheduleSilentVoiceRestart(500);
      }
    };

    return recognition;
  }

  function startMicrophoneRecognition() {
    if (
      !voiceAnswerEnabled ||
      voicePauseForFeedback ||
      voiceCalloutRunning ||
      locked ||
      voiceRecognitionRunning ||
      results.classList.contains("show") ||
      !workspace.classList.contains("show") ||
      abacusHint.classList.contains("show")
    ) {
      return;
    }

    if (!voiceRecognition) {
      voiceRecognition =
        createVoiceRecognition();
    }

    if (!voiceRecognition) {
      updateVoiceUi();
      return;
    }

    bgmEngine.ensureContext();
    bgmEngine.ensureRunning();

    if (
      bgmOn &&
      currentBgm &&
      !bgmEngine.hasActiveSource()
    ) {
      bgmEngine.play(
        currentBgm,
        true
      );
    }

    // マイクを開いているだけではBGMを止めない。
    // 発話検知(onspeechstart)が来た瞬間だけ0%へ下げる。
    voiceSpeechDetected = false;
    refreshBgmVolume();

    try {
      voiceRecognition.start();
    } catch (error) {
      voiceRecognitionRunning = false;
      voiceSpeechDetected = false;
      refreshBgmVolume();
      scheduleSilentVoiceRestart(
        500
      );
    }
  }

  function hideQuestionForVoiceCallout() {
    questionCard.classList.add(
      "voice-waiting"
    );
  }

  function revealQuestionAfterVoiceCallout() {
    questionCard.classList.remove(
      "voice-waiting"
    );

    // 表示された瞬間にレイアウトを確定。
    void questionCard.offsetWidth;
  }

  function speakGowasanThenListen() {
    if (
      !voiceAnswerEnabled ||
      voicePauseForFeedback ||
      voiceCalloutRunning ||
      locked ||
      voiceRecognitionRunning ||
      results.classList.contains("show") ||
      !workspace.classList.contains("show") ||
      abacusHint.classList.contains("show")
    ) {
      return;
    }

    voiceCalloutRunning = true;
    gowasanSpokenForIndex =
      index;

    // 表示はカタカナで固定。
    hideQuestionForVoiceCallout();

    updateVoiceUi(
      "音声回答：ゴワサン！"
    );

    voicePauseForFeedback = true;
    refreshBgmVolume();
    bgmEngine.ensureRunning();

    const beginListening = () => {
      voiceCalloutRunning = false;
      voicePauseForFeedback = false;

      if (
        !voiceAnswerEnabled ||
        locked ||
        results.classList.contains("show")
      ) {
        refreshBgmVolume();
        return;
      }

      // ゴワサンの語尾が回答用マイクへ入らないよう、短い無音時間を置く。
      bgmEngine.setVolume(
        BGM_VOLUME_LISTENING,
        0.06
      );

      updateVoiceUi(
        "音声回答：まもなく問題スタート"
      );

      setTimeout(() => {
        if (
          !voiceAnswerEnabled ||
          locked ||
          results.classList.contains("show")
        ) {
          refreshBgmVolume();
          return;
        }

        voiceSpeechDetected = false;
        refreshBgmVolume();
        startMicrophoneRecognition();
      }, MIC_PRE_SILENCE_MS);
    };

    if (
      !("speechSynthesis" in window) ||
      typeof SpeechSynthesisUtterance ===
        "undefined"
    ) {
      beginListening();
      return;
    }

    cancelAppSpeech();

    // Chrome/Androidでは getVoices() の準備が遅れることがある。
    // 日本語音声が得られてから発声し、英語系フォールバックを避ける。
    waitForJapaneseVoice(
      1400
    ).then((voice) => {
      if (
        !voiceAnswerEnabled ||
        locked ||
        results.classList.contains("show")
      ) {
        voiceCalloutRunning = false;
        voicePauseForFeedback = false;
        refreshBgmVolume();
        return;
      }

      const utterance =
        new SpeechSynthesisUtterance(
          "ゴワサン！"
        );

      utterance.lang =
        "ja-JP";

      // 速すぎず、ピッチを上げず、日本語の短い掛け声として発声。
      utterance.rate =
        0.92;

      utterance.pitch =
        1.00;

      utterance.volume = appMasterVolume;

      if (voice) {
        utterance.voice =
          voice;
      }

      let finished = false;

      const done = () => {
        if (finished) {
          return;
        }

        finished = true;
        beginListening();
      };

      utterance.onend =
        done;

      utterance.onerror =
        done;

      try {
        window.speechSynthesis.resume();
      } catch (error) {}

      speakWithAppVolume(
        utterance
      );
    }).catch(() => {
      // 音声取得に失敗してもゲームは止めない。
      beginListening();
    });
  }

  function startVoiceRecognition() {
    // 同じ問題ですでに「ゴワサン」を言っていたら、
    // どこから呼ばれても二度と言わず、マイクだけ再開する。
    if (
      gowasanSpokenForIndex ===
      index
    ) {
      scheduleSilentVoiceRestart(
        120
      );
      return;
    }

    speakGowasanThenListen();
  }

  function setVoiceAnswerEnabled(
    enabled
  ) {
    voiceAnswerEnabled =
      Boolean(enabled);

    const hintIsOpen =
      abacusHint.classList.contains(
        "show"
      );

    // 珠ヒント表示中は、チャレンジ本体の音声回答フローへ切り替えない。
    // ここで「ゴワサン」やrenderQuestion()を動かすと、
    // ヒント画面が消えたり問題表示が空になったりするため、
    // 珠ヒント専用マイクだけをON/OFFする。
    if (hintIsOpen) {
      clearVoiceRestartTimer();
      voiceCalloutRunning = false;
      voicePauseForFeedback = false;
      stopVoiceRecognition();

      if (voiceAnswerEnabled) {
        bgmEngine.ensureContext();
        bgmEngine.ensureRunning();
        startBgmKeepAlive();

        updateVoiceUi(
          "音声回答：ON（珠ヒントで使います）"
        );
      } else {
        stopHintQuestionRecognition();

        if ("speechSynthesis" in window) {
          cancelAppSpeech();
        }

        updateVoiceUi(
          "音声回答：OFF"
        );
      }

      // 現在の珠ヒントSTEPをそのまま保ち、
      // マイクONなら補数質問・最終回答だけ自動聞き取りへ、
      // OFFなら数字タップ/手元入力へ切り替える。
      if (
        hintManualSteps.length &&
        !hintAutoAnimating
      ) {
        renderManualHintStep(
          hintManualIndex,
          false
        );
      }

      refreshBgmVolume();
      return;
    }

    if (voiceAnswerEnabled) {
      bgmEngine.ensureContext();
      bgmEngine.ensureRunning();

      if (
        bgmOn &&
        currentBgm &&
        !bgmEngine.hasActiveSource()
      ) {
        bgmEngine.play(
          currentBgm,
          true
        );
      }

      startBgmKeepAlive();

      updateVoiceUi(
        "音声回答：開始します…"
      );

      // 通常のチャレンジ画面でだけ「ゴワサン」フローを使う。
      hideQuestionForVoiceCallout();

      startVoiceRecognition();
      return;
    }

    voiceCalloutRunning = false;
    voicePauseForFeedback = false;

    if ("speechSynthesis" in window) {
      cancelAppSpeech();
    }

    stopVoiceRecognition();
    stopBgmKeepAlive();

    refreshBgmVolume();

    // 珠ヒント表示中はこの分岐に来ない。
    // 通常のチャレンジ画面だけ問題表示を更新する。
    if (
      workspace.classList.contains("show") &&
      currentMode
    ) {
      renderQuestion(true);
    }

    updateVoiceUi(
      "音声回答：OFF"
    );
  }


  function getJapaneseVoice() {
    if (!("speechSynthesis" in window)) {
      return null;
    }

    const voices =
      window.speechSynthesis.getVoices();

    const japaneseVoices =
      voices.filter((voice) =>
        String(
          voice.lang || ""
        )
          .toLowerCase()
          .startsWith("ja")
      );

    if (
      japaneseVoices.length === 0
    ) {
      return null;
    }

    // 端末に複数音声がある場合は、日本語専用音声を最優先する。
    // Android Chrome では "Google 日本語" が自然な場合が多い。
    const preferredNames = [
      "google 日本語",
      "google japanese",
      "日本語",
      "japanese",
      "nanami",
      "haruka",
      "sayaka",
      "kyoko",
      "otoya",
      "ichiro"
    ];

    const scored =
      japaneseVoices.map(
        (voice) => {
          const name =
            String(
              voice.name || ""
            ).toLowerCase();

          const lang =
            String(
              voice.lang || ""
            ).toLowerCase();

          let score = 0;

          if (
            lang === "ja-jp"
          ) {
            score += 300;
          }

          preferredNames.forEach(
            (preferred, idx) => {
              if (
                name.includes(
                  preferred.toLowerCase()
                )
              ) {
                score +=
                  220 - idx * 8;
              }
            }
          );

          if (
            voice.localService
          ) {
            score += 25;
          }

          // 日本語候補に入っていても名前に英語系表記が混ざるものは避ける。
          if (
            /english|en-us|en-gb|american|british/.test(
              name
            )
          ) {
            score -= 500;
          }

          return {
            voice,
            score
          };
        }
      );

    scored.sort(
      (a, b) =>
        b.score - a.score
    );

    return (
      scored[0]?.voice ||
      japaneseVoices[0]
    );
  }

  function waitForJapaneseVoice(
    timeoutMs = 1400
  ) {
    return new Promise((resolve) => {
      if (
        !("speechSynthesis" in window)
      ) {
        resolve(null);
        return;
      }

      const immediate =
        getJapaneseVoice();

      if (immediate) {
        resolve(immediate);
        return;
      }

      let finished = false;
      const startedAt =
        performance.now();

      const finish = (voice) => {
        if (finished) {
          return;
        }

        finished = true;

        try {
          window.speechSynthesis.removeEventListener(
            "voiceschanged",
            onVoicesChanged
          );
        } catch (error) {}

        resolve(
          voice || null
        );
      };

      const check = () => {
        const voice =
          getJapaneseVoice();

        if (voice) {
          finish(voice);
          return;
        }

        if (
          performance.now() -
            startedAt >=
          timeoutMs
        ) {
          finish(null);
          return;
        }

        setTimeout(
          check,
          80
        );
      };

      const onVoicesChanged = () => {
        const voice =
          getJapaneseVoice();

        if (voice) {
          finish(voice);
        }
      };

      try {
        window.speechSynthesis.addEventListener(
          "voiceschanged",
          onVoicesChanged
        );
      } catch (error) {}

      check();
    });
  }

  function speakAnswerFeedback(
    ok,
    streak,
    onDone = null,
    overrideMessage = null
  ) {
    voicePauseForFeedback = true;
    stopVoiceRecognition();
    refreshBgmVolume();
    bgmEngine.ensureRunning();

    let completed = false;

    const finishFeedback = () => {
      if (completed) {
        return;
      }

      completed = true;
      voicePauseForFeedback = false;
      refreshBgmVolume();
      bgmEngine.ensureRunning();

      if (
        typeof onDone ===
        "function"
      ) {
        onDone();
      }
    };

    if (
      !("speechSynthesis" in window) ||
      typeof SpeechSynthesisUtterance ===
        "undefined"
    ) {
      finishFeedback();
      return;
    }

    const message =
      overrideMessage ||
      (
        !ok
          ? "残念！"
          : streak >= 2
            ? `お見事！${streak}問連続正解！`
            : "お見事！"
      );

    try {
      cancelAppSpeech();
      window.speechSynthesis.resume();
    } catch (error) {}

    // 次の問題の「ゴワサン」で途中キャンセルされないよう、
    // この音声が終わってから問題を進める。
    const fallbackTimer =
      setTimeout(
        finishFeedback,
        3200
      );

    waitForJapaneseVoice(
      1200
    ).then((voice) => {
      if (completed) {
        return;
      }

      const utterance =
        new SpeechSynthesisUtterance(
          message
        );

      utterance.lang = "ja-JP";
      utterance.rate = 0.96;
      utterance.pitch = 1.03;
      // すべての画面に共通の音量。
      utterance.volume = appMasterVolume;

      if (voice) {
        utterance.voice = voice;
      }

      const done = () => {
        clearTimeout(
          fallbackTimer
        );
        finishFeedback();
      };

      utterance.onend = done;
      utterance.onerror = done;

      try {
        window.speechSynthesis.resume();
        speakWithAppVolume(
          utterance
        );
      } catch (error) {
        done();
      }
    }).catch(() => {
      clearTimeout(
        fallbackTimer
      );
      finishFeedback();
    });
  }

  function setRainbowForStreak(streak, card = questionCard) {
    const vars = [
      "--rb1", "--rb2", "--rb3", "--rb4",
      "--rb5", "--rb6", "--rb7", "--rb8"
    ];

    if (streak < 6) {
      vars.forEach((name) =>
        card.style.removeProperty(name)
      );
      return;
    }

    // 6問連続正解以降は、正解するたび少しずつ配色を変える。
    const baseHue =
      ((streak - 6) * 47) % 360;

    const offsets = [
      0, 46, 92, 138,
      184, 230, 276, 322
    ];

    offsets.forEach(
      (offset, index) => {
        const hue =
          (baseHue + offset) % 360;

        card.style.setProperty(
          `--rb${index + 1}`,
          `hsl(${hue} 92% 58%)`
        );
      }
    );
  }

  function updateStreakFrame(streak, card = questionCard) {
    card.classList.remove(
      "streak5",
      "streak6",
      "streak10",
      "question-flash"
    );

    card.style.borderColor = "";
    card.style.borderWidth = "";
    card.style.boxShadow = "";

    setRainbowForStreak(streak, card);

    if (streak >= 10) {
      card.classList.add(
        "streak10"
      );
      return;
    }

    if (streak >= 6) {
      card.classList.add(
        "streak6"
      );
    }
  }

  function flashQuestionFrameIfNeeded(streak = correctStreak, card = questionCard) {
    card.classList.remove(
      "question-flash"
    );

    if (streak < 10) {
      return;
    }

    // reflowして、毎問きちんと発光アニメーションを再生。
    void card.offsetWidth;

    card.classList.add(
      "question-flash"
    );

    setTimeout(() => {
      card.classList.remove(
        "question-flash"
      );
    }, 1200);
  }

  function loadTutorialProgress() {
    try {
      const raw =
        localStorage.getItem(
          LEARNING_PROGRESS_STORAGE_KEY
        );

      if (!raw) {
        return {
          cleared: {}
        };
      }

      const parsed =
        JSON.parse(raw);

      if (
        !parsed ||
        typeof parsed !== "object"
      ) {
        return {
          cleared: {}
        };
      }

      if (
        !parsed.cleared ||
        typeof parsed.cleared !== "object"
      ) {
        parsed.cleared = {};
      }

      return parsed;
    } catch (error) {
      return {
        cleared: {}
      };
    }
  }

  function saveTutorialProgress() {
    try {
      localStorage.setItem(
        LEARNING_PROGRESS_STORAGE_KEY,
        JSON.stringify(
          learningProgress
        )
      );
    } catch (error) {}
  }

  function allTutorialLessons() {
    return Object.values(
      learningCategories
    ).flatMap(
      (category) =>
        category.lessons
    );
  }

  function isTutorialLessonCleared(
    lessonId
  ) {
    return Boolean(
      learningProgress
        .cleared[lessonId]
    );
  }

  function tutorialCategoryStats(
    categoryKey
  ) {
    const lessons =
      learningCategories[
        categoryKey
      ].lessons;

    const cleared =
      lessons.filter(
        (lesson) =>
          isTutorialLessonCleared(
            lesson.id
          )
      ).length;

    return {
      cleared,
      total: lessons.length
    };
  }

  function tutorialLessonUnlocked(
    categoryKey,
    index
  ) {
    if (index === 0) {
      return true;
    }

    const lessons =
      learningCategories[
        categoryKey
      ].lessons;

    return isTutorialLessonCleared(
      lessons[index - 1].id
    );
  }

  function updateTutorialOverallProgress() {
    const all =
      allTutorialLessons();

    const cleared =
      all.filter(
        (lesson) =>
          isTutorialLessonCleared(
            lesson.id
          )
      ).length;

    const total =
      all.length;

    learningOverallText.textContent =
      `全体 ${cleared} / ${total} STEP クリア`;

    learningOverallBar.style.width =
      `${total ? (cleared / total) * 100 : 0}%`;
  }

  function runUiCleanup(callback) {
    try {
      callback();
    } catch (error) {
      // Do not allow cleanup failures to block navigation.
    }
  }

  function forceHomeView() {
    root.querySelector("#hosuView")?.classList.remove("show");
    workspace.classList.remove("show");
    results.classList.remove("show");
    menuView.classList.add("hidden");
    learningView.classList.remove("show");
    anzanView.classList.remove("show");
    settingsView.classList.remove("show");
    weaknessView.classList.remove("show");
    kukuView.classList.remove("show");
    homeView.classList.remove("hidden");
  }

  function forceChallengeMenuView() {
    root.querySelector("#hosuView")?.classList.remove("show");
    homeView.classList.add("hidden");
    learningView.classList.remove("show");
    anzanView.classList.remove("show");
    settingsView.classList.remove("show");
    weaknessView.classList.remove("show");
    kukuView.classList.remove("show");
    workspace.classList.remove("show");
    results.classList.remove("show");
    menuView.classList.remove("hidden");
  }

  function showHome() {
    learningInterrupt();
    const abandoningChallenge =
      workspace.classList.contains(
        "show"
      ) &&
      !results.classList.contains(
        "show"
      ) &&
      Boolean(currentMode);

    if (abandoningChallenge) {
      clearChallengeResumeState();
    }

    // First switch the view. Camera/audio cleanup happens afterwards.
    forceHomeView();

    runUiCleanup(discardChallengeVideoSession);
    runUiCleanup(stopTimer);
    runUiCleanup(stopBgm);
    runUiCleanup(hideSorobanHint);
    runUiCleanup(stopLearningAnimation);
    runUiCleanup(stopAnzanSession);
    runUiCleanup(stopKukuSession);
    runUiCleanup(() => setVoiceAnswerEnabled(false));
    runUiCleanup(closeRankingModal);
    runUiCleanup(closeRankCelebration);
    runUiCleanup(updateRankUi);

    currentMode = null;
  }

  function showChallengeMenu() {
    learningInterrupt();
    forceChallengeMenuView();
    refreshChallengeMenuUi();

    runUiCleanup(stopLearningAnimation);
    runUiCleanup(stopAnzanSession);
    runUiCleanup(stopTimer);
    runUiCleanup(stopBgm);
    runUiCleanup(hideSorobanHint);
    runUiCleanup(() => setVoiceAnswerEnabled(false));
    runUiCleanup(closeRankCelebration);
  }

  function showWeaknessHome() {
    learningInterrupt();
    stopTimer();
    stopBgm();
    hideSorobanHint();
    stopLearningAnimation();
    stopAnzanSession();
    stopKukuSession();
    setVoiceAnswerEnabled(false);

    homeView.classList.add("hidden");
    menuView.classList.add("hidden");
    learningView.classList.remove("show");
    anzanView.classList.remove("show");
    settingsView.classList.remove("show");
    kukuView.classList.remove("show");
    workspace.classList.remove("show");
    results.classList.remove("show");
    weaknessView.classList.add("show");

    renderWeaknessChallengeGrid();
  }

  function showLearningHome() {
    learningInterrupt();
    stopTimer();
    stopBgm();
    hideSorobanHint();
    setVoiceAnswerEnabled(false);

    homeView.classList.add(
      "hidden"
    );
    menuView.classList.add(
      "hidden"
    );
    anzanView.classList.remove(
      "show"
    );
    settingsView.classList.remove(
      "show"
    );
    weaknessView.classList.remove(
      "show"
    );
    kukuView.classList.remove(
      "show"
    );
    workspace.classList.remove(
      "show"
    );
    results.classList.remove(
      "show"
    );

    learningView.classList.add(
      "show"
    );

    learningCategoryView.classList.remove(
      "hidden"
    );
    learningStageView.classList.add(
      "hidden"
    );
    learningLessonView.classList.add(
      "hidden"
    );

    learningCurrentCategory = null;
    stopLearningAnimation();
    renderLearningCategories();
  }

  function renderLearningCategories() {
    learningCategoryGrid.innerHTML =
      "";

    updateTutorialOverallProgress();

    Object.entries(
      learningCategories
    ).forEach(
      ([key, category]) => {
        const stats =
          tutorialCategoryStats(
            key
          );

        const card =
          document.createElement(
            "article"
          );

        card.className =
          "learning-category-card";

        const starsFilled =
          "★".repeat(
            stats.cleared
          );

        const starsEmpty =
          "☆".repeat(
            stats.total -
            stats.cleared
          );

        card.innerHTML = `
          <div class="learning-category-symbol">${category.symbol}</div>
          <div class="learning-category-title">${category.title}</div>
          <div class="learning-category-desc">${category.desc}</div>
          <div class="learning-stars">${starsFilled}${starsEmpty} ${stats.cleared}/${stats.total}</div>
        `;

        const button =
          document.createElement(
            "button"
          );

        button.type =
          "button";

        button.className =
          "primary";

        button.textContent =
          stats.cleared === 0
            ? "STEP 1から学ぶ"
            : stats.cleared === stats.total
              ? "復習する"
              : "続きから学ぶ";

        button.addEventListener(
          "click",
          () => {
            showLearningStages(
              key
            );
          }
        );

        card.appendChild(button);
        learningCategoryGrid.appendChild(
          card
        );
      }
    );
  }

  function showLearningStages(
    categoryKey
  ) {
    learningCurrentCategory =
      categoryKey;

    stopLearningAnimation();

    learningCategoryView.classList.add(
      "hidden"
    );

    learningLessonView.classList.add(
      "hidden"
    );

    learningStageView.classList.remove(
      "hidden"
    );

    const category =
      learningCategories[
        categoryKey
      ];

    learningStageKicker.textContent =
      `${category.symbol} ${category.title}`;

    learningStageHeading.textContent =
      "少しずつSTEP UP";

    learningStageGrid.innerHTML =
      "";

    category.lessons.forEach(
      (lesson, index) => {
        const unlocked =
          tutorialLessonUnlocked(
            categoryKey,
            index
          );

        const cleared =
          isTutorialLessonCleared(
            lesson.id
          );

        const card =
          document.createElement(
            "article"
          );

        card.className =
          "learning-stage-card";

        if (!unlocked) {
          card.classList.add(
            "locked"
          );
        }

        if (cleared) {
          card.classList.add(
            "cleared"
          );
        }

        card.innerHTML = `
          <div class="learning-stage-no">STEP ${index + 1}</div>
          <div class="learning-stage-title">${lesson.title}</div>
          <div class="learning-stage-desc">${lesson.desc}</div>
          <div class="learning-stage-status">${
            cleared
              ? "★ クリア"
              : unlocked
                ? "○ 学習できます"
                : "🔒 1つ前のSTEPをクリアすると開きます"
          }</div>
        `;

        const button =
          document.createElement(
            "button"
          );

        button.type =
          "button";

        button.disabled =
          !unlocked;

        button.textContent =
          cleared
            ? "もう一度見る"
            : unlocked
              ? "学習スタート"
              : "ロック中";

        if (unlocked) {
          button.className =
            "primary";

          button.addEventListener(
            "click",
            () => {
              openLearningLesson(
                categoryKey,
                index
              );
            }
          );
        }

        card.appendChild(
          button
        );

        learningStageGrid.appendChild(
          card
        );
      }
    );
  }

  function buildLearningBoard(
    digitCount
  ) {
    learningRods = [];
    learningSorobanBoard.innerHTML =
      "";

    const safeCount =
      Math.max(
        1,
        digitCount
      );

    for (
      let i = 0;
      i < safeCount;
      i += 1
    ) {
      const place =
        10 ** (
          safeCount -
          1 -
          i
        );

      const rod =
        document.createElement(
          "div"
        );

      rod.className =
        "soroban-rod";

      rod.dataset.place =
        String(place);

      const line =
        document.createElement(
          "div"
        );

      line.className =
        "rod-line";

      rod.appendChild(
        line
      );

      const upper =
        document.createElement(
          "div"
        );

      upper.className =
        "soroban-bead upper-bead";

      rod.appendChild(
        upper
      );

      const lowers = [];

      for (
        let j = 0;
        j < 4;
        j += 1
      ) {
        const bead =
          document.createElement(
            "div"
          );

        bead.className =
          "soroban-bead lower-bead";

        bead.style.top =
          `${112 + j * 18}px`;

        rod.appendChild(
          bead
        );

        lowers.push(
          bead
        );
      }

      const label =
        document.createElement(
          "div"
        );

      label.className =
        "rod-place";

      label.textContent =
        shortPlaceName(
          place
        );

      rod.appendChild(
        label
      );

      learningSorobanBoard.appendChild(
        rod
      );

      learningRods.push({
        rod,
        place,
        upper,
        lowers
      });
    }
  }

  function showLearningNumber(
    value,
    activePlace = null
  ) {
    const safeValue =
      Math.max(
        0,
        Math.floor(
          Math.abs(
            Number(value) || 0
          )
        )
      );

    const digits =
      String(safeValue)
        .padStart(
          learningRods.length,
          "0"
        )
        .slice(
          -learningRods.length
        )
        .split("")
        .map(Number);

    learningRods.forEach(
      (rodInfo, index) => {
        setRodDigit(
          rodInfo,
          digits[index]
        );

        rodInfo.rod
          .classList.toggle(
            "active",
            activePlace !== null &&
            rodInfo.place ===
              activePlace
          );
      }
    );
  }

  function currentLearningLesson() {
    if (!learningCurrentCategory) {
      return null;
    }

    return learningCategories[
      learningCurrentCategory
    ].lessons[
      learningCurrentLessonIndex
    ] || null;
  }

  function updateLearningVoiceUi() {
    learningVoiceBtn.textContent =
      learningVoiceEnabled
        ? "🔊 音声解説 ON"
        : "🔊 音声解説 OFF";

    learningVoiceBtn.classList.toggle(
      "on",
      learningVoiceEnabled
    );

    learningVoiceNote.textContent =
      learningVoiceEnabled
        ? "音声解説：ON　ひとつずつ、ゆっくり説明します。"
        : "音声解説をONにすると、珠の動きをゆっくり読み上げます。";
  }

  function stopLearningNarration() {
    learningNarrationToken += 1;

    if (
      "speechSynthesis" in window
    ) {
      cancelAppSpeech();
    }
  }

  function learningNarrationText(
    lesson,
    frameIndex
  ) {
    const scripts =
      learningVoiceScripts[
        lesson.id
      ];

    if (
      Array.isArray(scripts) &&
      scripts[frameIndex]
    ) {
      return scripts[
        frameIndex
      ];
    }

    return String(
      lesson.frames[
        frameIndex
      ]?.text || ""
    );
  }

  function speakLearningFrame(
    lesson,
    frameIndex
  ) {
    if (!learningVoiceEnabled) {
      return;
    }

    if (
      !("speechSynthesis" in window) ||
      typeof SpeechSynthesisUtterance ===
        "undefined"
    ) {
      learningVoiceNote.textContent =
        "このブラウザでは音声解説を使えません。";
      return;
    }

    const message =
      learningNarrationText(
        lesson,
        frameIndex
      );

    if (!message) {
      return;
    }

    // 前の説明が残っていたら止めて、
    // 現在の珠の動きだけを説明する。
    cancelAppSpeech();

    const token =
      ++learningNarrationToken;

    const utterance =
      new SpeechSynthesisUtterance(
        message
      );

    utterance.lang = "ja-JP";

    // 子どもが珠を見ながら追えるよう、
    // 通常の読み上げよりかなりゆっくり。
    utterance.rate = 0.72;
    utterance.pitch = 1.18;
    utterance.volume = appMasterVolume;

    const voice =
      getJapaneseVoice();

    if (voice) {
      utterance.voice = voice;
    }

    utterance.onend = () => {
      if (
        token !==
        learningNarrationToken
      ) {
        return;
      }
    };

    utterance.onerror =
      utterance.onend;

    speakWithAppVolume(
      utterance
    );
  }

  function setLearningVoiceEnabled(
    enabled,
    savePreference = true
  ) {
    learningVoiceEnabled =
      Boolean(enabled);

    if (savePreference) {
      preferredLearningVoiceEnabled =
        learningVoiceEnabled;

      saveBooleanSetting(
        LEARNING_VOICE_SETTING_KEY,
        preferredLearningVoiceEnabled
      );

      updateSettingsUi();
    }

    stopLearningNarration();
    updateLearningVoiceUi();

    if (
      learningVoiceEnabled &&
      currentLearningLesson()
    ) {
      // ONにした瞬間から説明と珠の動きをそろえるため、
      // 動画を先頭から再生する。
      runLearningAnimation(
        true
      );
    }
  }

  function stopLearningAnimation() {
    learningAnimationToken += 1;
    learningAnimationPaused = false;
    stopLearningNarration();
  }

  function renderLearningAnimationState(
    lesson,
    frameIndex
  ) {
    const lastIndex =
      lesson.frames.length - 1;

    const isStart =
      frameIndex === 0;

    const isAnswer =
      frameIndex === lastIndex &&
      lastIndex > 0;

    learningVideoCard.classList.remove(
      "is-active",
      "is-answer"
    );

    if (isAnswer) {
      learningVideoCard.classList.add(
        "is-answer"
      );
    } else if (!isStart) {
      learningVideoCard.classList.add(
        "is-active"
      );
    }

    // ループ先頭へ戻ったら、必ず「?」へ戻す。
    if (!isAnswer) {
      learningExampleProblem.textContent =
        lesson.example || "";
      return;
    }

    // 完成形では「?」だけを赤い答えへ置き換える。
    const answer =
      String(
        lesson.frames[lastIndex].value
      );

    const example =
      String(
        lesson.example || ""
      );

    const questionMarkIndex =
      example.lastIndexOf("?");

    if (questionMarkIndex < 0) {
      learningExampleProblem.textContent =
        `${example} ${answer}`;
      return;
    }

    const before =
      example.slice(
        0,
        questionMarkIndex
      );

    const after =
      example.slice(
        questionMarkIndex + 1
      );

    learningExampleProblem.innerHTML =
      `${before}<span class="learning-answer-red">${answer}</span>${after}`;
  }

  function renderLearningFrame(
    frameIndex
  ) {
    const lesson =
      currentLearningLesson();

    if (!lesson) {
      return;
    }

    const safeIndex =
      Math.max(
        0,
        Math.min(
          lesson.frames.length - 1,
          frameIndex
        )
      );

    const frame =
      lesson.frames[
        safeIndex
      ];

    learningCurrentFrame =
      safeIndex;

    learningStepText.textContent =
      frame.text;

    learningFrameCounter.textContent =
      `${safeIndex + 1} / ${lesson.frames.length}`;

    renderLearningAnimationState(
      lesson,
      safeIndex
    );

    showLearningNumber(
      frame.value,
      frame.place
    );

    speakLearningFrame(
      lesson,
      safeIndex
    );
  }

  function runLearningAnimation(
    restart = true
  ) {
    const lesson =
      currentLearningLesson();

    if (!lesson) {
      return;
    }

    if (restart) {
      stopLearningAnimation();
      learningCurrentFrame = 0;
    }

    const token =
      learningAnimationToken;

    learningAnimationPaused =
      false;

    learningPauseBtn.textContent =
      "Ⅱ 一時停止";

    const showNext = () => {
      if (
        token !==
        learningAnimationToken
      ) {
        return;
      }

      if (
        learningAnimationPaused
      ) {
        setTimeout(
          showNext,
          180
        );
        return;
      }

      const frameBeingShown =
        learningCurrentFrame;

      renderLearningFrame(
        frameBeingShown
      );

      learningCurrentFrame += 1;

      if (
        learningCurrentFrame >=
        lesson.frames.length
      ) {
        learningCurrentFrame = 0;

        // 完成形を十分見せる。
        // 音声ONのときは、読み上げが終わる時間も確保する。
        const answerDelay =
          learningVoiceEnabled
            ? 7200
            : 3200;

        setTimeout(
          showNext,
          answerDelay
        );
        return;
      }

      // 音声OFFはこれまでのゆっくり速度。
      // 音声ONは、短い解説を聞き終えてから次へ進む。
      const frameDelay =
        learningVoiceEnabled
          ? (
              frameBeingShown === 0
                ? 7600
                : 6800
            )
          : (
              frameBeingShown === 0
                ? 3800
                : 3200
            );

      setTimeout(
        showNext,
        frameDelay
      );
    };

    showNext();
  }

  function renderLearningQuiz(
    lesson
  ) {
    learningQuizQuestion.textContent =
      lesson.quiz.q;

    learningQuizOptions.innerHTML =
      "";

    learningQuizFeedback.textContent =
      "";

    learningClearActions.classList.remove(
      "show"
    );

    lesson.quiz.options.forEach(
      (option) => {
        const button =
          document.createElement(
            "button"
          );

        button.type =
          "button";

        button.className =
          "learning-quiz-option";

        button.textContent =
          option;

        button.addEventListener(
          "click",
          () => {
            const correct =
              option ===
              lesson.quiz.answer;

            learningResponse(tutorialStampAttempt,0,correct,"answer",option,"button",lesson.quiz.answer);
            const qr=tutorialStampAttempt?.questions["0"];
            if(qr)qr.explanation_used=true;
            if(correct){recordSharedStampAnswer(tutorialStampAttempt,0,qr?.first_correct===true);completeSharedStamp(tutorialStampAttempt,null);}
            else learningPhase("explanation");
            learningQuizOptions
              .querySelectorAll(
                "button"
              )
              .forEach(
                (item) => {
                  item.disabled =
                    true;

                  if (
                    item.textContent ===
                    lesson.quiz.answer
                  ) {
                    item.classList.add(
                      "correct-choice"
                    );
                  }
                }
              );

            if (correct) {
              learningProgress
                .cleared[
                  lesson.id
                ] = true;

              saveTutorialProgress();

              learningQuizFeedback
                .textContent =
                "★ クリア！ 次のSTEPが開きました。";

              learningQuizFeedback
                .style.color =
                "#2f6a43";

              learningClearActions
                .classList.add(
                  "show"
                );

              renderLearningCategories();
            } else {
              button.classList.add(
                "wrong-choice"
              );

              learningQuizFeedback
                .textContent =
                `もう一度動画を見てみよう。正解は「${lesson.quiz.answer}」。`;

              learningQuizFeedback
                .style.color =
                "#a14428";

              learningClearActions
                .classList.add(
                  "show"
                );
            }
          }
        );

        learningQuizOptions
          .appendChild(
            button
          );
      }
    );
  }

  function openLearningLesson(
    categoryKey,
    lessonIndex
  ) {
    learningCurrentCategory =
      categoryKey;

    learningCurrentLessonIndex =
      lessonIndex;

    const category =
      learningCategories[
        categoryKey
      ];

    const lesson =
      category.lessons[
        lessonIndex
      ];
    tutorialStampAttempt=beginSharedStamp("calculation",lesson.id,1);
    learningMenu(tutorialStampAttempt,"soroban:tutorial:"+lesson.id,"soroban:lesson:"+lesson.id,lessonIndex+1);
    learningQuestion(tutorialStampAttempt,0,{a:lesson.id,op:"lesson",b:1,quiz:lesson.quiz,example:lesson.example},"choice");
    learningPhase("explanation");

    learningCategoryView
      .classList.add(
        "hidden"
      );

    learningStageView
      .classList.add(
        "hidden"
      );

    learningLessonView
      .classList.remove(
        "hidden"
      );

    learningLessonKicker.textContent =
      `${category.symbol} ${category.title} / STEP ${lessonIndex + 1}`;

    learningLessonTitle.textContent =
      lesson.title;

    learningVoiceEnabled =
      preferredLearningVoiceEnabled;

    updateLearningVoiceUi();

    learningExampleProblem.textContent =
      lesson.example || "";

    learningVideoCard.classList.remove(
      "is-active",
      "is-answer"
    );

    learningBasicText.textContent =
      lesson.basic;

    learningTroubleText.textContent =
      lesson.trouble;

    learningRuleBox.textContent =
      lesson.rule;

    const maxValue =
      Math.max(
        0,
        ...lesson.frames.map(
          (frame) =>
            Math.abs(
              Number(
                frame.value
              ) || 0
            )
        )
      );

    const digitCount =
      Math.max(
        1,
        String(
          Math.floor(
            maxValue
          )
        ).length
      );

    buildLearningBoard(
      digitCount
    );

    renderLearningQuiz(
      lesson
    );

    renderLearningFrame(
      0
    );

    runLearningAnimation(
      true
    );

    const nextExists =
      Boolean(
        category.lessons[
          lessonIndex + 1
        ]
      );

    learningNextBtn.textContent =
      nextExists
        ? "次のSTEPへ"
        : "STEP一覧へ";
  }

  function goNextLearningLesson() {
    const category =
      learningCategories[
        learningCurrentCategory
      ];

    const nextIndex =
      learningCurrentLessonIndex +
      1;

    if (
      category &&
      category.lessons[
        nextIndex
      ] &&
      tutorialLessonUnlocked(
        learningCurrentCategory,
        nextIndex
      )
    ) {
      openLearningLesson(
        learningCurrentCategory,
        nextIndex
      );
      return;
    }

    showLearningStages(
      learningCurrentCategory
    );
  }

  function stopKukuRecognition() {
    consumeKukuSpeechTime();

    if (!kukuRecognition) {
      kukuListening = false;
      kukuSpeechDetected = false;
      kukuSpeechStartedAt = 0;
      refreshBgmVolume();
      return;
    }

    try {
      kukuRecognition.onend = null;
      kukuRecognition.abort();
    } catch (error) {}

    kukuRecognition = null;
    kukuListening = false;
    kukuSpeechDetected = false;
    kukuSpeechStartedAt = 0;
    refreshBgmVolume();
  }

  function stopKukuTimer() {
    consumeKukuSpeechTime();

    if (kukuTimerHandle) {
      clearInterval(
        kukuTimerHandle
      );

      kukuTimerHandle = null;
    }

    kukuSpeechDetected = false;
    kukuSpeechStartedAt = 0;
  }

  function stopKukuSession() {
    clearTimeout(kukuScrollTimer);
    kukuScrollCheck += 1;
    stopKukuTableReading();
    if (kukuView.classList.contains("show") && !kukuGameView.classList.contains("hidden")) stopBgm();
    kukuRunToken += 1;
    stopKukuRecognition();
    stopKukuTimer();
    kukuPromptSpeaking = false;
    kukuLocked = true;
    refreshBgmVolume();
  }

  function showKukuHome() {
    learningInterrupt();
    stopTimer(); stopBgm(); hideSorobanHint(); stopLearningAnimation(); stopAnzanSession(); stopKukuSession(); setVoiceAnswerEnabled(false);
    homeView.classList.add("hidden"); menuView.classList.add("hidden"); learningView.classList.remove("show"); anzanView.classList.remove("show"); settingsView.classList.remove("show"); weaknessView.classList.remove("show"); workspace.classList.remove("show"); results.classList.remove("show");
    kukuView.classList.add("show"); kukuMenuView.classList.remove("hidden"); kukuGameView.classList.add("hidden"); kukuResultView.classList.add("hidden");
    $("#kukuTableView").classList.add("hidden");
    renderKukuMedalSummaries();
  }

  function shuffleKuku(items) {
    const result = [...items];
    for (let i = result.length - 1; i > 0; i -= 1) { const j = Math.floor(Math.random() * (i + 1)); [result[i], result[j]] = [result[j], result[i]]; }
    return result;
  }

  function buildKukuQuestions(level) {
    if (level === 1 || level === 2) {
      const dan = randomInt(1, 9);
      const ascending = level === 1 ? true : Math.random() < 0.5;
      const multipliers = Array.from({ length: 10 }, (_, index) => index + 1);
      if (!ascending) multipliers.reverse();
      return multipliers.map((value) => ({ a: dan, b: value, answer: dan * value, direction: ascending ? "昇順" : "降順" }));
    }

    const all = [];
    for (let a = 1; a <= 9; a += 1) {
      for (let b = 1; b <= 10; b += 1) {
        all.push({ a, b, answer: a * b, direction: "ランダム" });
      }
    }

    const shuffled = shuffleKuku(all);
    if (level === 3) return shuffled.slice(0, 10);
    if (level === 4) return shuffled.slice(0, 30);
    return shuffled;
  }

  function updateKukuAnswerDisplay() { kukuAnswerDisplay.textContent = kukuAnswerBuffer || "\u00a0"; }

  function updateKukuButtons() {
    kukuVoiceBtn.textContent =
      kukuVoiceEnabled
        ? "🎤 音声回答 ON"
        : "🎤 音声回答 OFF";

    kukuVoiceBtn.classList.toggle(
      "on",
      kukuVoiceEnabled
    );
  }

  function consumeKukuSpeechTime() {
    if (
      kukuLevel === 1 ||
      !kukuSpeechDetected ||
      kukuSpeechStartedAt <= 0
    ) {
      return;
    }

    const now =
      performance.now();

    const elapsed =
      Math.max(
        0,
        now - kukuSpeechStartedAt
      );

    kukuRemainingMs =
      Math.max(
        0,
        kukuRemainingMs - elapsed
      );

    kukuSpeechStartedAt =
      now;
  }

  function updateKukuTimer() {
    if (kukuLevel === 1) {
      kukuTimer.textContent =
        "時間なし";

      kukuTimer.classList.remove(
        "warn"
      );

      return;
    }

    const safe =
      Math.max(
        0,
        Math.ceil(
          kukuRemainingMs / 1000
        )
      );

    kukuSeconds = safe;

    const minutes =
      Math.floor(safe / 60);

    const secondsPart =
      safe % 60;

    kukuTimer.textContent =
      `${minutes}:${String(
        secondsPart
      ).padStart(2, "0")}`;

    kukuTimer.classList.toggle(
      "warn",
      safe <= 10
    );
  }

  function startKukuTimer() {
    stopKukuTimer();

    if (kukuLevel === 1) {
      kukuRemainingMs = 0;
      updateKukuTimer();
      return;
    }

    const limitSeconds =
      kukuLevel === 4
        ? 90
        : kukuLevel === 5
          ? 240
          : 60;

    kukuRemainingMs =
      limitSeconds * 1000;

    kukuSpeechStartedAt = 0;
    updateKukuTimer();

    kukuTimerHandle =
      setInterval(() => {
        if (!kukuSpeechDetected) {
          return;
        }

        consumeKukuSpeechTime();
        updateKukuTimer();

        if (kukuRemainingMs <= 0) {
          stopKukuTimer();
          finishKukuMode(true);
        }
      }, 50);
  }

  const KUKU_CHANT_STEMS = {
    1: {1:"いんいちが",2:"いんにが",3:"いんさんが",4:"いんしが",5:"いんごが",6:"いんろくが",7:"いんしちが",8:"いんはちが",9:"いんくが"},
    2: {1:"にいちが",2:"ににんが",3:"にさんが",4:"にしが",5:"にご",6:"にろく",7:"にしち",8:"にはち",9:"にく"},
    3: {1:"さんいちが",2:"さんにが",3:"さざんが",4:"さんし",5:"さんご",6:"さぶろく",7:"さんしち",8:"さんぱ",9:"さんく"},
    4: {1:"しいちが",2:"しにが",3:"しさん",4:"しし",5:"しご",6:"しろく",7:"ししち",8:"しは",9:"しく"},
    5: {1:"ごいちが",2:"ごに",3:"ごさん",4:"ごし",5:"ごご",6:"ごろく",7:"ごしち",8:"ごは",9:"ごっく"},
    6: {1:"ろくいちが",2:"ろくに",3:"ろくさん",4:"ろくし",5:"ろくご",6:"ろくろく",7:"ろくしち",8:"ろくは",9:"ろっく"},
    7: {1:"しちいちが",2:"しちに",3:"しちさん",4:"しちし",5:"しちご",6:"しちろく",7:"しちしち",8:"しちは",9:"しちく"},
    8: {1:"はちいちが",2:"はちに",3:"はっさん",4:"はっし",5:"はちご",6:"はちろく",7:"はちしち",8:"はっぱ",9:"はっく"},
    9: {1:"くいちが",2:"くに",3:"くさん",4:"くし",5:"くご",6:"くろく",7:"くしち",8:"くは",9:"くく"}
  };

  function getKukuSpokenPrompt(question) {
    // 中級・上級・特級・名人は、一般的な九九の唱え方に統一。
    if (kukuLevel >= 2) {
      const stem =
        KUKU_CHANT_STEMS?.[question.a]?.[question.b];

      if (stem) {
        return `${stem}？`;
      }
    }

    // 初級だけは式との対応を覚えやすいよう通常の読み上げ。
    return `${question.a}掛ける${question.b}は？`;
  }

  function getKukuSpokenAnswer(question) {
    // 不正解時も九九の唱え方で、式と答えを読み上げる。
    const digits = ["", "いち", "に", "さん", "よん", "ご", "ろく", "なな", "はち", "きゅう"];
    const tens = Math.floor(question.answer / 10);
    const ones = question.answer % 10;
    const singleAnswers = ["", "いち", "に", "さん", "し", "ご", "ろく", "しち", "はち", "く"];
    const answerReading =
      tens > 0
        ? `${tens === 1 ? "" : digits[tens]}じゅう${digits[ones]}`
        : singleAnswers[ones];
    const tenStems = ["", "いんじゅう", "にじゅう", "さんじゅう", "しじゅう", "ごじゅう", "ろくじゅう", "しちじゅう", "はちじゅう", "くじゅう"];
    const stem = KUKU_CHANT_STEMS?.[question.a]?.[question.b] ||
      (question.b === 10 ? tenStems[question.a] : "");

    return `${stem}${answerReading}。`;
  }

  let kukuTableToken = 0;
  let kukuTableTimer = null;
  let kukuTablePlaying = false;

  function stopKukuTableReading() {
    if(learningActive?.assignment_context?.assessment===false)learningInterrupt();
    kukuTableToken += 1;
    clearTimeout(kukuTableTimer);
    if (kukuTablePlaying) cancelAppSpeech();
    kukuTablePlaying = false;
    $("#kukuTableStopBtn").disabled = true;
    root.querySelectorAll("#kukuTableGrid .reading").forEach((row) => row.classList.remove("reading"));
    $("#kukuTableStatus").textContent = "";
  }

  function buildKukuTable() {
    const grid = $("#kukuTableGrid");
    if (grid.children.length) return;
    for (let a = 1; a <= 9; a += 1) {
      const card = document.createElement("article");
      card.className = "kuku-table-card";
      const heading = document.createElement("h3");
      heading.textContent = `${a}の段`;
      const play = document.createElement("button");
      play.type = "button";
      play.textContent = "▶ 読み上げ";
      play.setAttribute("aria-label", `${a}の段を読み上げ`);
      play.addEventListener("click", () => readKukuTableRow(a));
      heading.appendChild(play);card.appendChild(heading);
      const table = document.createElement("table");
      table.setAttribute("aria-label", `${a}の段`);
      const body = document.createElement("tbody");
      for (let b = 1; b <= 9; b += 1) {
        const row = document.createElement("tr");
        row.dataset.kukuTableCell = `${a}-${b}`;
        const equation = document.createElement("td");
        equation.textContent = `${a} × ${b} = ${a * b}`;
        const reading = document.createElement("td");
        reading.textContent = getKukuSpokenAnswer({a,b,answer:a*b}).replace(/。$/, "");
        row.append(equation,reading);body.appendChild(row);
      }
      table.appendChild(body);card.appendChild(table);grid.appendChild(card);
    }
  }

  function showKukuTable() {
    learningInterrupt();
    showKukuHome();
    kukuMenuView.classList.add("hidden");
    $("#kukuTableView").classList.remove("hidden");
    buildKukuTable();
  }

  function readKukuTableRow(a) {
    stopKukuTableReading();
    if (!("speechSynthesis" in window) || typeof SpeechSynthesisUtterance === "undefined") {
      $("#kukuTableStatus").textContent = "このブラウザでは読み上げを使えません。";
      return;
    }
    tutorialStampAttempt=beginSharedStamp("kuku","read",1);
    learningMenu(tutorialStampAttempt,`soroban:kuku:read:${a}`,`soroban:kuku:${a}`,a);
    if(tutorialStampAttempt)tutorialStampAttempt.assignment_context={assessment:false};
    learningQuestion(tutorialStampAttempt,0,{a,op:"reading",b:9},"reading");
    if(tutorialStampAttempt?.questions["0"])tutorialStampAttempt.questions["0"].explanation_used=true;
    learningPhase("explanation");
    kukuTablePlaying = true;
    $("#kukuTableStopBtn").disabled = false;
    const token = kukuTableToken;
    const active = () => token === kukuTableToken && kukuTablePlaying &&
      kukuView.classList.contains("show") && !$("#kukuTableView").classList.contains("hidden");
    const read = (b,voice) => {
      if (!active()) return;
      root.querySelectorAll("#kukuTableGrid .reading").forEach((row) => row.classList.remove("reading"));
      if (b > 9) {
        if(learningActive?.assignment_context?.assessment===false){learningActive.questions["0"].completed=true;learningSnapshot(learningActive,"completed");learningActive=null;learningClock=null;sendSharedStamp();}
        stopKukuTableReading();
        $("#kukuTableStatus").textContent = `${a}の段を読み終わりました。`;
        return;
      }
      $(`[data-kuku-table-cell="${a}-${b}"]`).classList.add("reading");
      $("#kukuTableStatus").textContent = `${a}の段：${a} × ${b} = ${a*b}`;
      const utterance = new SpeechSynthesisUtterance(getKukuSpokenAnswer({a,b,answer:a*b}));
      utterance.lang = "ja-JP";utterance.rate = 1.0;
      if (voice) utterance.voice = voice;
      let ended = false;
      utterance.onend = () => {
        if (ended || !active()) return;
        ended = true;clearTimeout(kukuTableTimer);
        kukuTableTimer = setTimeout(() => read(b+1,voice),250);
      };
      const failed = () => {
        if (!active()) return;
        stopKukuTableReading();
        $("#kukuTableStatus").textContent = "読み上げが止まりました。もう一度、読み上げを押してね。";
      };
      utterance.onerror = failed;
      kukuTableTimer = setTimeout(failed,12000);
      try { window.speechSynthesis.resume();speakWithAppVolume(utterance); }
      catch (error) { failed(); }
    };
    waitForJapaneseVoice(1000).then((voice) => read(1,voice)).catch(() => read(1,null));
  }

  $("#kukuTableOpenBtn").addEventListener("click", showKukuTable);
  $("#kukuTableBackBtn").addEventListener("click", showKukuHome);
  $("#kukuTableStopBtn").addEventListener("click", stopKukuTableReading);

  function speakKukuQuestion(question, onDone) {
    stopKukuRecognition();
    let finished = false;
    const done = () => { if (finished) return; finished = true; kukuPromptSpeaking = false; refreshBgmVolume(); if (typeof onDone === "function") onDone(); };
    if (!("speechSynthesis" in window) || typeof SpeechSynthesisUtterance === "undefined") { done(); return; }
    kukuPromptSpeaking = true; refreshBgmVolume();
    try { cancelAppSpeech(); window.speechSynthesis.resume(); } catch (error) {}
    waitForJapaneseVoice(1000).then((voice) => {
      const utterance = new SpeechSynthesisUtterance(getKukuSpokenPrompt(question));
      utterance.lang = "ja-JP"; utterance.rate = 1.18; utterance.pitch = 1.02; utterance.volume = appMasterVolume;
      if (voice) utterance.voice = voice;
      utterance.onend = done; utterance.onerror = done;
      speakWithAppVolume(utterance);
      setTimeout(done, 1900);
    }).catch(done);
  }

  function startKukuVoiceRecognition() {
    if (
      !kukuVoiceEnabled ||
      kukuLocked ||
      kukuPromptSpeaking
    ) {
      return;
    }

    const Recognition =
      getSpeechRecognitionClass();

    if (!Recognition) {
      kukuPrompt.textContent =
        "このブラウザでは音声回答を使えません。";
      return;
    }

    stopKukuRecognition();

    const recognition =
      new Recognition();
    appDiagnostics.observeRecognition(recognition);

    kukuRecognition =
      recognition;

    let accepted = false;
    let mayRetry = true;

    recognition.lang =
      "ja-JP";

    recognition.continuous =
      false;

    recognition.interimResults =
      false;

    recognition.maxAlternatives =
      10;

    recognition.onstart = () => {
      kukuAnswerBuffer = "";
      updateKukuAnswerDisplay();

      kukuListening = true;
      kukuSpeechDetected = false;
      kukuSpeechStartedAt = 0;

      kukuPrompt.textContent =
        "🎤 答えを言ってね";
    };

    recognition.onspeechstart = () => {
      kukuSpeechDetected = true;
      kukuSpeechStartedAt =
        performance.now();

      kukuPrompt.textContent =
        "🎤 聞いています…";
    };

    recognition.onspeechend = () => {
      consumeKukuSpeechTime();

      kukuSpeechDetected = false;
      kukuSpeechStartedAt = 0;

      kukuPrompt.textContent =
        "🎤 確認中…";
    };

    recognition.onresult = (
      event
    ) => {
      cmLastInput="speech";
      const result =
        event.results?.[
          event.resultIndex || 0
        ] ||
        event.results?.[0];

      const selected =
        selectBestNumericSpeech(
          result
        );

      if (!selected) {
        kukuPrompt.textContent =
          "🎤 もう一度、答えを言ってね";

        return;
      }

      accepted = true;
      mayRetry = false;

      kukuAnswerBuffer =
        String(
          selected.value
        );

      updateKukuAnswerDisplay();
      submitKukuAnswer();
    };

    recognition.onerror = (
      event
    ) => {
      if(learningActive)cmEmit(learningActive,"learning_activity",{activity_type:"recognition_failed",substep_id:null,result:null,observation_basis:"speech_api_error:"+String(event?.error||"unknown")},learningActive.questions[String(learningClock?.index)]);
      consumeKukuSpeechTime();

      kukuListening = false;
      kukuSpeechDetected = false;
      kukuSpeechStartedAt = 0;

      const errorName =
        event?.error || "";

      if (
        errorName === "not-allowed"
      ) {
        mayRetry = false;

        kukuPrompt.textContent =
          "マイクの権限がありません。ブラウザでマイクを許可してください。";

        return;
      }

      // 一時的な認識失敗では、音声回答を止めない。
      mayRetry = true;

      kukuPrompt.textContent =
        "🎤 もう一度、答えを言ってね";
    };

    recognition.onend = () => {
      consumeKukuSpeechTime();

      kukuRecognition = null;
      kukuListening = false;
      kukuSpeechDetected = false;
      kukuSpeechStartedAt = 0;

      if (
        mayRetry &&
        !accepted &&
        kukuVoiceEnabled &&
        !kukuLocked &&
        !kukuPromptSpeaking
      ) {
        setTimeout(() => {
          if (
            kukuVoiceEnabled &&
            !kukuLocked &&
            !kukuPromptSpeaking &&
            !kukuRecognition
          ) {
            startKukuVoiceRecognition();
          }
        }, 120);
      }
    };

    try {
      recognition.start();
    } catch (error) {
      kukuRecognition = null;
      kukuListening = false;
      kukuSpeechDetected = false;
      kukuSpeechStartedAt = 0;

      kukuPrompt.textContent =
        "🎤 もう一度、答えを言ってね";

      setTimeout(() => {
        if (
          kukuVoiceEnabled &&
          !kukuLocked &&
          !kukuPromptSpeaking &&
          !kukuRecognition
        ) {
          startKukuVoiceRecognition();
        }
      }, 160);
    }
  }

  function kukuChallengeStreak() {
    // 通常チャレンジ12問に対する連続正解率へ換算する。
    return Math.floor(kukuStreak * 12 / Math.max(1, kukuQuestions.length));
  }

  function updateKukuChallengeEffects(force = false) {
    const streak = kukuChallengeStreak();
    updateStreakFrame(streak, $("#kukuGameView .kuku-game-card"));
    playBgmForStreak(streak, force);
  }

  let kukuScrollTimer = null;
  let kukuScrollCheck = 0;

  function resetKukuScrollPosition(token = kukuRunToken) {
    clearTimeout(kukuScrollTimer);
    const check = ++kukuScrollCheck;
    let attempts = 0;
    const active = () => check === kukuScrollCheck && token === kukuRunToken &&
      kukuView.classList.contains("show") && !kukuGameView.classList.contains("hidden");
    // レベル選択・回答ボタンに残ったフォーカスが画面を引き戻すのを防ぐ。
    try {
      const focused = document.activeElement;
      if (focused && root.contains(focused)) focused.blur();
    } catch (error) {}
    const verify = () => {
      if (!active()) return;
      const nodes = [document.scrollingElement, document.documentElement, document.body];
      const windows = [window];
      // window.scrollYではなく、iframeを包むstMain等がスクロールしている場合も確認する。
      try {
        let child = window;
        for (let depth = 0; depth < 8 && child.parent && child.parent !== child; depth += 1) {
          const parent = child.parent;
          const parentDoc = parent.document;
          const frame = child.frameElement || Array.from(parentDoc.querySelectorAll("iframe"))
            .find((element) => element.contentWindow === child);
          for (let node = frame; node; node = node.parentElement) nodes.push(node);
          nodes.push(parentDoc.scrollingElement, parentDoc.documentElement, parentDoc.body);
          windows.push(parent);
          child = parent;
        }
      } catch (error) { /* 別オリジンではscrollIntoViewによる上端合わせを使う。 */ }
      const moved = nodes.some((node) => node && (node.scrollTop > 1 || node.scrollLeft > 1)) ||
        windows.some((surface) => (surface.scrollY || 0) > 1);
      const clipped = kukuView.getBoundingClientRect().top < -1;
      if (attempts === 0 || moved || clipped) {
        try { kukuView.scrollIntoView({block:"start",inline:"nearest",behavior:"instant"}); } catch (error) {}
        nodes.forEach((node) => {
          if (!node) return;
          node.scrollTop = 0; node.scrollLeft = 0;
        });
        windows.forEach((surface) => {
          try { surface.scrollTo({top:0,left:0,behavior:"instant"}); } catch (error) {}
        });
      }
      attempts += 1;
      // マイク開始・レイアウト確定が遅れるスマホでも、2秒間は実際の位置を再確認する。
      if (attempts < 21) kukuScrollTimer = setTimeout(verify,100);
    };
    verify();
  }

  function startKukuMode(...args) {
    return appDiagnostics.measure("startKukuMode", () => startKukuModeMeasured.apply(this,args));
  }
  function startKukuModeMeasured(level) {
    stopKukuSession();
    kukuLevel = Math.max(1, Math.min(5, Number(level) || 1));
    kukuQuestions = buildKukuQuestions(kukuLevel);
    kukuStampAttempt = beginSharedStamp("kuku",kukuLevelName(kukuLevel),kukuQuestions.length);
    learningMenu(kukuStampAttempt,`soroban:kuku:${kukuLevel}`,"soroban:multiplication",kukuLevel);
    kukuQuestionIndex = 0; kukuCorrect = 0; kukuStreak = 0; kukuAnswerBuffer = ""; kukuVoiceEnabled = preferredVoiceAnswerEnabled; kukuLocked = true;
    kukuMenuView.classList.add("hidden"); kukuResultView.classList.add("hidden"); kukuGameView.classList.remove("hidden");
    updateKukuButtons();
    updateKukuAnswerDisplay();

    bgmEngine.ensureContext();
    updateKukuChallengeEffects(true);
    startBgmKeepAlive();

    startKukuTimer();
    runKukuQuestion();
  }

  function runKukuQuestion(...args) {
    return appDiagnostics.measure("runKukuQuestion", () => runKukuQuestionMeasured.apply(this,args));
  }
  function runKukuQuestionMeasured() {
    stopKukuRecognition();
    if (kukuQuestionIndex >= kukuQuestions.length) { finishKukuMode(false); return; }
    const token = ++kukuRunToken; const question = kukuQuestions[kukuQuestionIndex];
    learningQuestion(kukuStampAttempt,kukuQuestionIndex,question);
    flashQuestionFrameIfNeeded(kukuChallengeStreak(), $("#kukuGameView .kuku-game-card"));
    kukuLocked = true; kukuAnswerBuffer = ""; updateKukuAnswerDisplay();
    kukuQCount.textContent = `${kukuQuestionIndex + 1} / ${kukuQuestions.length}`; kukuCorrectCount.textContent = `正解 ${kukuCorrect}`; kukuEquation.textContent = `${question.a} × ${question.b} = ?`;
    kukuFeedback.textContent = ""; kukuFeedback.className = "kuku-feedback"; kukuPrompt.textContent = getKukuSpokenPrompt(question);
    resetKukuScrollPosition(token);
    if(learningClock)learningClock.cmPhase="prompt";
    speakKukuQuestion(question, () => { if (token !== kukuRunToken || kukuQuestionIndex >= kukuQuestions.length) return; kukuLocked = false; if(learningClock)learningClock.cmPhase="thinking";cmEmit(kukuStampAttempt,"learning_activity",{activity_type:"answer_acceptance_started",substep_id:null,result:null,observation_basis:"application_unlocked"},kukuStampAttempt?.questions[String(kukuQuestionIndex)]); resetKukuScrollPosition(token); if (kukuVoiceEnabled) setTimeout(startKukuVoiceRecognition, 60); else kukuPrompt.textContent = "数字をタップして答えてね"; });
  }

  function submitKukuAnswer() {
    if (kukuLocked || kukuQuestionIndex >= kukuQuestions.length) return;
    const raw = String(kukuAnswerBuffer || "").trim();
    if (!raw) { kukuFeedback.textContent = "答えを入力してください"; kukuFeedback.className = "kuku-feedback bad"; return; }
    const user = Number(raw); if (!Number.isFinite(user)) return;
    kukuLocked = true; stopKukuRecognition();
    const question = kukuQuestions[kukuQuestionIndex]; const ok = user === question.answer;
    learningResponse(kukuStampAttempt,kukuQuestionIndex,ok,"answer",user);
    if(!ok){const r=kukuStampAttempt?.questions[String(kukuQuestionIndex)];if(r)r.explanation_used=true;}
    recordSharedStampAnswer(kukuStampAttempt,kukuQuestionIndex,ok);
    if (ok) { kukuCorrect += 1; kukuStreak += 1; kukuFeedback.textContent = "お見事！"; kukuFeedback.className = "kuku-feedback good"; }
    else { kukuStreak = 0; kukuFeedback.textContent = `残念！ 答えは ${question.answer}`; kukuFeedback.className = "kuku-feedback bad"; }
    kukuCorrectCount.textContent =
      `正解 ${kukuCorrect}`;
    updateKukuChallengeEffects();
    const advance = () => { kukuQuestionIndex += 1; if (kukuQuestionIndex >= kukuQuestions.length) finishKukuMode(false); else runKukuQuestion(); };

    if(!ok){const cq=kukuStampAttempt?.questions[String(kukuQuestionIndex)];cmSupport(kukuStampAttempt,cq,"answer",null,null,true);cmSupport(kukuStampAttempt,cq,"explanation",null,null,true); }
    const kukuFeedbackVoice = ok
      ? "お見事！"
      : `残念！${getKukuSpokenAnswer(question)}`;

    speakAnswerFeedback(
      ok,
      kukuStreak,
      advance,
      kukuFeedbackVoice
    );
  }

  function finishKukuMode(timeup = false) {
    if (
      !kukuResultView.classList.contains(
        "hidden"
      )
    ) {
      return;
    }

    if(timeup&&kukuStampAttempt){kukuStampAttempt.end_reason="timed_out";const cq=kukuStampAttempt.questions[String(kukuQuestionIndex)];if(cq&&!cq.completed){learningTick();cmResponse(kukuStampAttempt,cq,null,null,null,null,"timed_out");}}
    stopKukuRecognition();
    stopKukuTimer();
    kukuPromptSpeaking = false;
    kukuLocked = true;
    refreshBgmVolume();

    try {
      cancelAppSpeech();
    } catch (error) {}

    stopBgm();

    kukuGameView.classList.add(
      "hidden"
    );

    kukuResultView.classList.remove(
      "hidden"
    );

    kukuResultScore.textContent =
      `${kukuCorrect} / ${kukuQuestions.length}`;

    const kukuPerfect =
      kukuCorrect ===
      kukuQuestions.length;

    const challengeCount =
      incrementKukuChallengeCount(
        kukuLevel
      );

    const earnedMedal = awardKukuMedal(
      kukuLevel,
      kukuCorrect,
      kukuQuestions.length
    );

    completeSharedStamp(kukuStampAttempt,earnedMedal||'white');
    const medalText = earnedMedal
      ? `${kukuMedalLabel(earnedMedal)}メダルを1枚獲得しました。`
      : "";

    if (kukuPerfect) {
      kukuResultText.textContent =
        `お見事！パーフェクト！全問正解です。${medalText}${kukuLevelName(kukuLevel)}は今回で${challengeCount}回目です。`;
    } else if (timeup) {
      const limitLabel =
        kukuLevel === 4
          ? "90秒"
          : kukuLevel === 5
            ? "240秒"
            : "60秒";

      kukuResultText.textContent =
        `${limitLabel}終了。${kukuCorrect}問正解でした。${medalText}${kukuLevelName(kukuLevel)}は今回で${challengeCount}回目です。`;
    } else {
      kukuResultText.textContent =
        `間違えた九九を確認して、もう一度挑戦しましょう。${medalText}${kukuLevelName(kukuLevel)}は今回で${challengeCount}回目です。`;
    }

    // 終了するたびに、該当レベルの累計挑戦回数を必ず読み上げる。
    speakKukuFinishSummary({
      level: kukuLevel,
      challengeCount,
      perfect: kukuPerfect
    });
  }

  function stopAnzanSession() {
    anzanRunToken += 1;
    stopAnzanRecognition();
    anzanLocked = true;
  }

  function showAnzanHome() {
    learningInterrupt();
    stopTimer();
    stopBgm();
    hideSorobanHint();
    stopLearningAnimation();
    stopAnzanSession();
    stopKukuSession();

    homeView.classList.add(
      "hidden"
    );
    menuView.classList.add(
      "hidden"
    );
    learningView.classList.remove(
      "show"
    );
    settingsView.classList.remove(
      "show"
    );
    weaknessView.classList.remove(
      "show"
    );
    workspace.classList.remove(
      "show"
    );
    results.classList.remove(
      "show"
    );

    anzanView.classList.add(
      "show"
    );
    anzanMenuView.classList.remove(
      "hidden"
    );
    anzanGameView.classList.add(
      "hidden"
    );
    anzanResultView.classList.add(
      "hidden"
    );
  }

  function showSettings(...args) {
    return appDiagnostics.measure("showSettings", () => showSettingsMeasured.apply(this,args));
  }
  function showSettingsMeasured() {
    learningInterrupt();
    stopTimer();
    stopBgm();
    hideSorobanHint();
    stopLearningAnimation();
    stopAnzanSession();
    stopKukuSession();

    homeView.classList.add(
      "hidden"
    );
    menuView.classList.add(
      "hidden"
    );
    learningView.classList.remove(
      "show"
    );
    anzanView.classList.remove(
      "show"
    );
    weaknessView.classList.remove(
      "show"
    );
    workspace.classList.remove(
      "show"
    );
    results.classList.remove(
      "show"
    );

    settingsView.classList.add(
      "show"
    );

    updateSettingsUi();
  }

  function makeAnzanQuestion(
    level
  ) {
    let terms = [];
    let total = 0;

    if (level === 1) {
      const count = 3;

      for (
        let i = 0;
        i < count;
        i += 1
      ) {
        const value =
          randomInt(
            1,
            9
          );

        terms.push({
          op: i === 0
            ? ""
            : "＋",
          value
        });

        total += value;
      }

      return {
        terms,
        answer: total
      };
    }

    const count = 5;
    const minValue =
      level === 2
        ? 1
        : 10;
    const maxValue =
      level === 2
        ? 9
        : 49;

    const first =
      randomInt(
        level === 2
          ? 4
          : 25,
        level === 2
          ? 9
          : 49
      );

    terms.push({
      op: "",
      value: first
    });

    total = first;

    for (
      let i = 1;
      i < count;
      i += 1
    ) {
      let op = "＋";
      let value =
        randomInt(
          minValue,
          maxValue
        );

      if (
        Math.random() < 0.45 &&
        total > minValue
      ) {
        const maxSubtract =
          Math.min(
            maxValue,
            total
          );

        if (
          maxSubtract >= minValue
        ) {
          op = "－";
          value =
            randomInt(
              minValue,
              maxSubtract
            );
        }
      }

      if (op === "＋") {
        total += value;
      } else {
        total -= value;
      }

      terms.push({
        op,
        value
      });
    }

    return {
      terms,
      answer: total
    };
  }

  function updateAnzanAnswerDisplay() {
    anzanAnswerDisplay.textContent =
      anzanAnswerBuffer ||
      "\u00a0";
  }

  function startAnzanMode(
    level
  ) {
    stopAnzanSession();
    anzanVoiceEnabled = preferredVoiceAnswerEnabled;
    anzanVoiceBlocked = false;
    updateAnzanVoiceUi();

    anzanLevel =
      Number(level) || 1;

    anzanStampAttempt = beginSharedStamp("anzan",["","初級","中級","上級"][anzanLevel] || String(anzanLevel),ANZAN_TOTAL_QUESTIONS);
    learningMenu(anzanStampAttempt,`soroban:anzan:${anzanLevel}`,"soroban:mental_arithmetic",anzanLevel);
    anzanQuestionIndex = 0;
    anzanCorrect = 0;
    anzanLocked = false;

    anzanMenuView.classList.add(
      "hidden"
    );
    anzanResultView.classList.add(
      "hidden"
    );
    anzanGameView.classList.remove(
      "hidden"
    );

    anzanSpeedLabel.textContent =
      anzanSpeedInfo().label;

    runAnzanQuestion();
  }

  function runAnzanQuestion() {
    stopAnzanRecognition();

    const token =
      ++anzanRunToken;

    anzanLocked = true;
    anzanAnswerBuffer = "";
    updateAnzanAnswerDisplay();
    anzanVoiceStatus.textContent = "";

    anzanQuestion =
      makeAnzanQuestion(
        anzanLevel
      );

    anzanQCount.textContent =
      `${anzanQuestionIndex + 1} / ${ANZAN_TOTAL_QUESTIONS}`;

    anzanCorrectCount.textContent =
      `正解 ${anzanCorrect}`;

    anzanFeedback.textContent =
      "";

    anzanFeedback.className =
      "anzan-feedback";

    anzanAnswerArea.classList.add(
      "hidden"
    );

    anzanFlash.className =
      "anzan-flash ready";

    anzanFlash.textContent =
      "よーい";

    anzanHint.textContent =
      "数字を順番に見てね";

    const info =
      anzanSpeedInfo();

    let termIndex = 0;

    const showTerm = () => {
      if (
        token !== anzanRunToken
      ) {
        return;
      }

      if (
        termIndex >=
        anzanQuestion.terms.length
      ) {
        anzanFlash.className =
          "anzan-flash answer";

        anzanFlash.textContent =
          "＝ ?";

        anzanHint.textContent =
          anzanVoiceEnabled
            ? "答えを声で言ってね"
            : "答えを入力してね";

        anzanAnswerArea.classList.remove(
          "hidden"
        );

        anzanLocked = false;
        learningTick();if(learningClock)learningClock.cmPhase="thinking";cmEmit(anzanStampAttempt,"learning_activity",{activity_type:"answer_acceptance_started",substep_id:null,result:null,observation_basis:"flash_sequence_completed"},anzanStampAttempt?.questions[String(anzanQuestionIndex)]);

        if (
          anzanVoiceEnabled
        ) {
          // 答え画面になったらそのままマイクを開始。
          // BGMは流したまま、実際の発話時だけ自動で下げる。
          queueAnzanRecognition();
        }

        return;
      }

      if(termIndex===0){learningQuestion(anzanStampAttempt,anzanQuestionIndex,anzanQuestion,"flash_numeric");if(learningClock)learningClock.cmPhase="prompt";}
      const term =
        anzanQuestion.terms[
          termIndex
        ];

      anzanFlash.className =
        "anzan-flash";

      anzanFlash.textContent =
        `${term.op}${term.value}`;

      termIndex += 1;

      setTimeout(
        showTerm,
        info.delay
      );
    };

    setTimeout(
      showTerm,
      900
    );
  }

  function canListenAnzan() {
    return anzanVoiceEnabled && !anzanLocked && !document.hidden &&
      anzanQuestionIndex < ANZAN_TOTAL_QUESTIONS &&
      anzanView.classList.contains("show") && !anzanGameView.classList.contains("hidden");
  }

  function updateAnzanVoiceUi() {
    const button = $("#anzanVoiceBtn");
    button.textContent = anzanVoiceBlocked ? "🎤 マイクを再開" : anzanVoiceEnabled ? "🎤 音声回答 ON" : "🎤 音声回答 OFF";
    button.classList.toggle("on", anzanVoiceEnabled);
    button.setAttribute("aria-pressed", String(anzanVoiceEnabled));
  }

  function stopAnzanRecognition() {
    clearTimeout(anzanRecognitionTimer);
    clearTimeout(anzanVoiceSubmitTimer);
    anzanRecognitionTimer = null;
    anzanVoiceSubmitTimer = null;
    anzanVoicePending = false;
    const recognition = anzanRecognition;
    anzanRecognition = null;
    if (recognition) {
      recognition.onstart = recognition.onresult = recognition.onerror = recognition.onend = null;
      recognition.onspeechstart = recognition.onspeechend = null;
      try { recognition.abort(); } catch (error) {}
    }
    anzanListening = false;
    anzanListeningStartedAt = 0;
    anzanSpeechDetected = false;
    refreshBgmVolume();
  }

  function queueAnzanRecognition(delay = 180) {
    clearTimeout(anzanRecognitionTimer);
    anzanRecognitionTimer = null;
    if (!canListenAnzan() || anzanVoiceBlocked || anzanRecognition || anzanVoicePending) return;
    const token = anzanRunToken;
    anzanRecognitionTimer = setTimeout(() => {
      anzanRecognitionTimer = null;
      if (token === anzanRunToken && canListenAnzan() && !anzanRecognition && !anzanVoicePending) startAnzanVoiceRecognition();
    }, delay);
  }

  function startAnzanVoiceRecognition() {
    clearTimeout(anzanRecognitionTimer);
    anzanRecognitionTimer = null;
    if (!canListenAnzan() || anzanVoiceBlocked || anzanRecognition || anzanVoicePending) return;
    const Recognition = getSpeechRecognitionClass();
    if (!Recognition) {
      anzanVoiceBlocked = true;
      anzanVoiceStatus.textContent = "このブラウザでは音声回答を使えません。数字で答えてください。";
      updateAnzanVoiceUi();
      return;
    }
    const token = anzanRunToken;
    const questionIndex = anzanQuestionIndex;
    const recognition = new Recognition();
    appDiagnostics.observeRecognition(recognition);
    anzanRecognition = recognition;
    recognition.lang = "ja-JP";
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.maxAlternatives = 5;
    const current = () => recognition === anzanRecognition && token === anzanRunToken && canListenAnzan();
    const recoverIfEndMissing = (delay) => {
      clearTimeout(anzanRecognitionTimer);
      anzanRecognitionTimer = setTimeout(() => {
        anzanRecognitionTimer = null;
        if (current() && !anzanVoicePending) {
          stopAnzanRecognition();
          queueAnzanRecognition(200);
        }
      }, delay);
    };
    recognition.onstart = () => {
      if (!current()) return;
      clearTimeout(anzanRecognitionTimer);
      anzanRecognitionTimer = null;
      anzanListening = true;
      anzanListeningStartedAt = Date.now();
      anzanSpeechDetected = false;
      refreshBgmVolume();
      anzanVoiceStatus.textContent = "🎤 答えを言ってね";
    };
    recognition.onspeechstart = () => {
      if (!current()) return;
      anzanSpeechDetected = true;
      refreshBgmVolume();
      anzanVoiceStatus.textContent = "🎤 聞いています…";
    };
    recognition.onspeechend = () => {
      if (current()) anzanVoiceStatus.textContent = "🎤 確認中…";
    };
    recognition.onresult = (event) => {
      if (!current() || anzanVoicePending) return;
      const result = event.results?.[event.resultIndex || 0] || event.results?.[0];
      const selected = selectBestNumericSpeech(result);
      if (!selected) {
        anzanVoiceStatus.textContent = "数字だけを、もう一度言ってね。";
        recoverIfEndMissing(1200);
        return;
      }
      cmLastInput = "speech";
      anzanVoicePending = true;
      anzanAnswerBuffer = String(selected.value);
      updateAnzanAnswerDisplay();
      // Android: finish the result callback before submit stops/aborts its microphone.
      anzanVoiceSubmitTimer = setTimeout(() => {
        anzanVoiceSubmitTimer = null;
        if (anzanVoicePending && token === anzanRunToken && questionIndex === anzanQuestionIndex && canListenAnzan()) {
          submitAnzanAnswer();
        }
        anzanVoicePending = false;
      }, 0);
    };
    recognition.onerror = (event) => {
      if (!current()) return;
      const name = event?.error || "unknown";
      const fatal = ["not-allowed", "service-not-allowed", "audio-capture", "language-not-supported"].includes(name);
      if (learningActive) cmEmit(learningActive,"learning_activity",{activity_type:"recognition_failed",substep_id:null,result:null,observation_basis:"speech_api_error:"+name},learningActive.questions[String(learningClock?.index)]);
      anzanVoiceBlocked = fatal;
      stopAnzanRecognition();
      anzanVoiceStatus.textContent = name === "not-allowed" || name === "service-not-allowed"
        ? "マイクを許可して「マイクを再開」を押してください。"
        : fatal ? "マイクを確認して「マイクを再開」を押してください。"
        : "🎤 もう一度、答えを言ってね";
      updateAnzanVoiceUi();
      if (!fatal) queueAnzanRecognition(300);
    };
    recognition.onend = () => {
      if (recognition !== anzanRecognition) return;
      anzanRecognition = null;
      anzanListening = false;
      anzanListeningStartedAt = 0;
      anzanSpeechDetected = false;
      refreshBgmVolume();
      if (token === anzanRunToken && !anzanVoicePending) queueAnzanRecognition();
    };
    try {
      recognition.start();
      if (!anzanListening) recoverIfEndMissing(2000);
    } catch (error) {
      const fatal = ["NotAllowedError", "SecurityError"].includes(error?.name);
      anzanVoiceBlocked = fatal;
      stopAnzanRecognition();
      anzanVoiceStatus.textContent = fatal ? "マイクを許可して「マイクを再開」を押してください。" : "🎤 もう一度、答えを言ってね";
      updateAnzanVoiceUi();
      if (!fatal) queueAnzanRecognition(400);
    }
  }

  $("#anzanVoiceBtn").addEventListener("click", () => {
    if (anzanVoiceBlocked) { anzanVoiceBlocked = false; anzanVoiceEnabled = true; }
    else anzanVoiceEnabled = !anzanVoiceEnabled;
    stopAnzanRecognition();
    updateAnzanVoiceUi();
    anzanVoiceStatus.textContent = anzanVoiceEnabled ? "🎤 答え画面で聞き取ります" : "数字をタップして答えてね";
    if (canListenAnzan()) startAnzanVoiceRecognition();
  });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) stopAnzanRecognition();
    else queueAnzanRecognition();
  });

  function submitAnzanAnswer() {
    if (
      anzanLocked ||
      !anzanQuestion
    ) {
      return;
    }

    const raw =
      String(
        anzanAnswerBuffer || ""
      ).trim();

    if (!raw) {
      anzanFeedback.textContent =
        "答えを入力してください";
      anzanFeedback.className =
        "anzan-feedback bad";
      return;
    }

    const user =
      Number(raw);

    if (!Number.isFinite(user)) {
      return;
    }

    anzanLocked = true;
    stopAnzanRecognition();

    const ok =
      user ===
      anzanQuestion.answer;

    learningResponse(anzanStampAttempt,anzanQuestionIndex,ok,"answer",user);
    recordSharedStampAnswer(anzanStampAttempt,anzanQuestionIndex,ok);
    if (ok) {
      anzanCorrect += 1;
      anzanFeedback.textContent =
        "お見事！";
      anzanFeedback.className =
        "anzan-feedback good";
    } else {
      anzanFeedback.textContent =
        `残念！ 答えは ${anzanQuestion.answer}`;
      anzanFeedback.className =
        "anzan-feedback bad";
    }

    if(!ok)cmSupport(anzanStampAttempt,anzanStampAttempt?.questions[String(anzanQuestionIndex)],"answer",null,null,true);
    anzanCorrectCount.textContent =
      `正解 ${anzanCorrect}`;

    setTimeout(
      () => {
        anzanQuestionIndex += 1;

        if (
          anzanQuestionIndex >=
          ANZAN_TOTAL_QUESTIONS
        ) {
          finishAnzanMode();
        } else {
          runAnzanQuestion();
        }
      },
      1100
    );
  }

  function finishAnzanMode() {
    if (!anzanResultView.classList.contains('hidden')) return;
    completeSharedStamp(anzanStampAttempt,gradeSharedScore(anzanCorrect,ANZAN_TOTAL_QUESTIONS));
    stopAnzanSession();

    anzanGameView.classList.add(
      "hidden"
    );
    anzanResultView.classList.remove(
      "hidden"
    );

    anzanResultScore.textContent =
      `${anzanCorrect} / ${ANZAN_TOTAL_QUESTIONS}`;

    anzanResultText.textContent =
      anzanCorrect ===
        ANZAN_TOTAL_QUESTIONS
        ? "全問正解。次のレベルにも挑戦できます。"
        : "同じレベルを繰り返すと、数字を頭に残しやすくなります。";
  }

  function loadBooleanSetting(
    key,
    fallback
  ) {
    try {
      const raw =
        localStorage.getItem(
          key
        );

      if (raw === "true") {
        return true;
      }

      if (raw === "false") {
        return false;
      }
    } catch (error) {}

    return fallback;
  }

  function saveBooleanSetting(
    key,
    value
  ) {
    try {
      localStorage.setItem(
        key,
        String(
          Boolean(value)
        )
      );
    } catch (error) {}
  }

  function loadAnzanSpeed() {
    try {
      const value =
        localStorage.getItem(
          ANZAN_SPEED_SETTING_KEY
        );

      if (
        value === "slow" ||
        value === "normal" ||
        value === "fast"
      ) {
        return value;
      }
    } catch (error) {}

    return "slow";
  }

  function saveAnzanSpeed() {
    try {
      localStorage.setItem(
        ANZAN_SPEED_SETTING_KEY,
        anzanSpeed
      );
    } catch (error) {}
  }

  function anzanSpeedInfo() {
    if (anzanSpeed === "fast") {
      return {
        label: "はやい",
        delay: 850
      };
    }

    if (anzanSpeed === "normal") {
      return {
        label: "ふつう",
        delay: 1350
      };
    }

    return {
      label: "ゆっくり",
      delay: 2000
    };
  }

  function updateSettingsUi() {
    settingTimeValue.textContent =
      timeDisplayEnabled
        ? "表示する"
        : "表示しない";

    settingVoiceValue.textContent =
      preferredVoiceAnswerEnabled
        ? "ON"
        : "OFF";

    settingBgmValue.textContent =
      bgmOn
        ? "ON"
        : "OFF";

    settingLearningVoiceValue.textContent =
      preferredLearningVoiceEnabled
        ? "ON"
        : "OFF";

    settingAnzanSpeedValue.textContent =
      anzanSpeedInfo().label;

    updateRankUi();
  }

  function cycleAnzanSpeed() {
    anzanSpeed =
      anzanSpeed === "slow"
        ? "normal"
        : anzanSpeed === "normal"
          ? "fast"
          : "slow";

    saveAnzanSpeed();
    updateSettingsUi();
  }

  const TIME_DISPLAY_STORAGE_KEY =
    "soroban_time_display_enabled_v1";
  const LEGACY_TIME_LIMIT_STORAGE_KEY =
    "soroban_time_limit_enabled_v1";

  function loadTimeDisplaySetting() {
    try {
      const raw =
        localStorage.getItem(
          TIME_DISPLAY_STORAGE_KEY
        );

      if (raw === "true") {
        return true;
      }

      if (raw === "false") {
        return false;
      }

      // 旧「時間制限ON/OFF」は表示設定として引き継ぐ。
      const legacy =
        localStorage.getItem(
          LEGACY_TIME_LIMIT_STORAGE_KEY
        );

      if (legacy === "false") {
        return false;
      }
    } catch (error) {}

    return true;
  }

  function saveTimeDisplaySetting() {
    try {
      localStorage.setItem(
        TIME_DISPLAY_STORAGE_KEY,
        String(timeDisplayEnabled)
      );
    } catch (error) {}
  }

  function updateTimeLimitUi() {
    // 計測自体は常時5分。ここでは表示するかどうかだけ切り替える。
    timeLimitEnabled = true;

    timeLimitBtn.textContent =
      timeDisplayEnabled
        ? "表示する"
        : "表示しない";

    timeLimitBtn.classList.toggle(
      "off",
      !timeDisplayEnabled
    );

    modeTimeBadge.textContent =
      "12問 / 金メダル基準5分";

    root
      .querySelectorAll(
        ".time-chip"
      )
      .forEach((chip) => {
        chip.textContent =
          "金:5分以内";
      });

    statusSub.textContent =
      "12問・金メダル基準5分";

    timerEl.classList.toggle(
      "hidden",
      !timeDisplayEnabled
    );

    if (!workspace.classList.contains("show")) {
      return;
    }

    updateTimer();
  }

  function updateAnalysisVideoUi() {
    if (!analysisVideoToggle) {
      return;
    }

    analysisVideoToggle.textContent =
      analysisVideoEnabled
        ? "ON"
        : "OFF";

    analysisVideoToggle.classList.toggle(
      "on",
      analysisVideoEnabled
    );
  }

  function toggleAnalysisVideo() {
    analysisVideoEnabled =
      !analysisVideoEnabled;

    saveBooleanSetting(
      ANALYSIS_VIDEO_SETTING_KEY,
      analysisVideoEnabled
    );

    updateAnalysisVideoUi();
  }

  function releaseAnalysisCameraStream() {
    if (!analysisCameraStream) {
      if (analysisCameraPreview) {
        analysisCameraPreview.srcObject =
          null;
      }
      return;
    }

    analysisCameraStream
      .getTracks()
      .forEach((track) => {
        try {
          track.stop();
        } catch (error) {}
      });

    analysisCameraStream = null;

    if (analysisCameraPreview) {
      analysisCameraPreview.srcObject =
        null;
    }
  }

  function closeCameraSetup(
    stopStream = true
  ) {
    cameraSetupModal.classList.remove(
      "show"
    );

    root
      .querySelectorAll(
        ".mode-card.camera-setup-active"
      )
      .forEach((card) => {
        card.classList.remove(
          "camera-setup-active"
        );
      });

    if (stopStream) {
      releaseAnalysisCameraStream();
    }

    cameraBeginBtn.disabled = true;
  }

  function revokeSessionVideoUrl() {
    if (sessionVideoUrl) {
      try {
        URL.revokeObjectURL(
          sessionVideoUrl
        );
      } catch (error) {}
    }

    sessionVideoUrl = null;
    sessionVideoBlob = null;

  }

  function resetSessionVideoData() {
    revokeSessionVideoUrl();

    sessionVideoChunks = [];
    sessionVideoMimeType = "";
    sessionVideoStartedAtPerf = null;
    sessionVideoStartedAtIso = null;
    sessionVideoDurationMs = 0;
    sessionVideoActive = false;
    sessionVideoDiscardOnStop = false;
    sessionVideoMode = null;
    sessionQuestionMarks = [];
    reviewClipEndSec = null;

    recordingBadge.classList.remove(
      "show"
    );

    videoReviewPanel.classList.add(
      "hidden"
    );

    if (hintBtn) {
      hintBtn.disabled = false;
      hintBtn.classList.remove(
        "recording-disabled"
      );
      hintBtn.textContent =
        "珠ヒントを見る（手動＋音声）";
    }
  }

  function chooseSessionVideoMimeType() {
    if (
      typeof MediaRecorder ===
      "undefined"
    ) {
      return "";
    }

    const candidates = [
      "video/mp4;codecs=h264",
      "video/mp4",
      "video/webm;codecs=vp9",
      "video/webm;codecs=vp8",
      "video/webm"
    ];

    for (
      const candidate
      of candidates
    ) {
      try {
        if (
          MediaRecorder.isTypeSupported(
            candidate
          )
        ) {
          return candidate;
        }
      } catch (error) {}
    }

    return "";
  }

  async function openCameraSetup(
    mode,
    sourceButton = null
  ) {
    pendingVideoMode =
      mode;

    closeCameraSetup(true);

    // Streamlit components.html は高さの大きい iframe 内で動くため、
    // fixed/vh の全画面モーダルはスマホ実画面と一致しない。
    // 押したモードカードの直下へ設定パネル自体を移動する。
    const sourceCard =
      sourceButton
        ? sourceButton.closest(
            ".mode-card"
          )
        : null;

    let targetCard =
      sourceCard;

    if (!targetCard) {
      const retryButton =
        root.querySelector(
          `.start-mode[data-mode="${mode}"]`
        );

      targetCard =
        retryButton
          ? retryButton.closest(
              ".mode-card"
            )
          : null;
    }

    if (targetCard) {
      targetCard.classList.add(
        "camera-setup-active"
      );

      targetCard.appendChild(
        cameraSetupModal
      );
    }

    cameraSetupModal.classList.add(
      "show"
    );

    cameraBeginBtn.disabled = true;
    cameraSetupStatus.textContent =
      "インカメラを準備しています。ブラウザのカメラ許可をONにしてください。";

    requestAnimationFrame(
      () => {
        try {
          cameraSetupModal.scrollIntoView({
            behavior: "smooth",
            block: "nearest"
          });
        } catch (error) {}
      }
    );

    if (
      !navigator.mediaDevices ||
      !navigator.mediaDevices.getUserMedia ||
      typeof MediaRecorder ===
        "undefined"
    ) {
      cameraSetupStatus.textContent =
        "このブラウザでは動画撮影を開始できません。『撮影なしで開始』は利用できます。";
      return;
    }

    try {
      const stream =
        await navigator.mediaDevices
          .getUserMedia({
            video: {
              facingMode: {
                ideal: "user"
              },
              width: {
                ideal: 1280
              },
              height: {
                ideal: 960
              },
              aspectRatio: {
                ideal: 1.333333
              },
              frameRate: {
                ideal: 20,
                max: 24
              }
            },
            // 音声は録画へ入れない。
            // Web Speech APIの回答用マイクと競合させないため。
            audio: false
          });

      if (
        !cameraSetupModal.classList
          .contains("show")
      ) {
        stream
          .getTracks()
          .forEach((track) => {
            track.stop();
          });
        return;
      }

      analysisCameraStream =
        stream;

      analysisCameraPreview.srcObject =
        stream;

      try {
        await analysisCameraPreview.play();
      } catch (error) {}

      const track =
        stream.getVideoTracks()[0];

      const settings =
        track &&
        typeof track.getSettings ===
          "function"
          ? track.getSettings()
          : {};

      const sizeText =
        settings.width &&
        settings.height
          ? ` ${settings.width}×${settings.height}`
          : "";

      cameraSetupStatus.textContent =
        `準備完了${sizeText}。両手とそろばん全体が白い枠に入ればOKです。`;

      cameraBeginBtn.disabled =
        false;
    } catch (error) {
      cameraSetupStatus.textContent =
        `カメラを開始できませんでした。${error?.name || ""} 『撮影なしで開始』は利用できます。`;
    }
  }

  function videoElapsedMs() {
    if (
      sessionVideoStartedAtPerf ===
      null
    ) {
      return null;
    }

    return Math.max(
      0,
      performance.now() -
        sessionVideoStartedAtPerf
    );
  }

  function startChallengeVideoRecording(
    mode
  ) {
    if (
      !analysisCameraStream ||
      typeof MediaRecorder ===
        "undefined"
    ) {
      return false;
    }

    resetSessionVideoData();

    sessionVideoMode =
      mode;

    sessionVideoStartedAtIso =
      new Date().toISOString();

    sessionVideoStartedAtPerf =
      performance.now();

    sessionVideoActive = true;
    sessionVideoDiscardOnStop =
      false;

    const mimeType =
      chooseSessionVideoMimeType();

    const options = {
      videoBitsPerSecond:
        1200000
    };

    if (mimeType) {
      options.mimeType =
        mimeType;
    }

    try {
      sessionMediaRecorder =
        new MediaRecorder(
          analysisCameraStream,
          options
        );
    } catch (error) {
      sessionMediaRecorder =
        new MediaRecorder(
          analysisCameraStream
        );
    }

    sessionVideoMimeType =
      sessionMediaRecorder.mimeType ||
      mimeType ||
      "video/webm";

    sessionVideoChunks = [];

    sessionMediaRecorder.ondataavailable =
      (event) => {
        if (
          event.data &&
          event.data.size > 0
        ) {
          sessionVideoChunks.push(
            event.data
          );
        }
      };

    sessionMediaRecorder.onerror =
      () => {
        sessionVideoActive =
          false;

        recordingBadge.classList.remove(
          "show"
        );
      };

    sessionMediaRecorder.onstop =
      () => {
        sessionVideoActive =
          false;

        recordingBadge.classList.remove(
          "show"
        );

        const discard =
          sessionVideoDiscardOnStop;

        const chunks =
          sessionVideoChunks.slice();

        sessionVideoChunks = [];

        releaseAnalysisCameraStream();

        if (
          discard ||
          chunks.length === 0
        ) {
          if (discard) {
            revokeSessionVideoUrl();
          }

          sessionVideoDiscardOnStop =
            false;
          return;
        }

        const blob =
          new Blob(
            chunks,
            {
              type:
                sessionVideoMimeType ||
                chunks[0]?.type ||
                "video/webm"
            }
          );

        if (!blob.size) {
          return;
        }

        revokeSessionVideoUrl();

        sessionVideoBlob =
          blob;

        sessionVideoUrl =
          URL.createObjectURL(
            blob
          );

        videoReviewStatus.textContent =
          "録画が完了しました。学習ログは端末内に自動保存されています。";

        renderPostSessionCoaching();
      };

    try {
      sessionMediaRecorder.start(
        1000
      );
    } catch (error) {
      sessionVideoActive =
        false;
      releaseAnalysisCameraStream();
      return false;
    }

    recordingBadge.classList.add(
      "show"
    );

    return true;
  }

  function stopChallengeVideoRecording(
    discard = false
  ) {
    sessionVideoDiscardOnStop =
      Boolean(discard);

    if (
      sessionVideoStartedAtPerf !==
      null
    ) {
      sessionVideoDurationMs =
        videoElapsedMs() || 0;
    }

    sessionVideoActive = false;

    recordingBadge.classList.remove(
      "show"
    );

    if (!sessionMediaRecorder) {
      releaseAnalysisCameraStream();
      return;
    }

    try {
      if (
        sessionMediaRecorder.state ===
        "recording"
      ) {
        try {
          sessionMediaRecorder.requestData();
        } catch (error) {}

        sessionMediaRecorder.stop();
      } else {
        releaseAnalysisCameraStream();
      }
    } catch (error) {
      releaseAnalysisCameraStream();
    }
  }

  function discardChallengeVideoSession() {
    closeCameraSetup(true);
    pendingVideoMode = null;

    if (
      sessionMediaRecorder &&
      sessionMediaRecorder.state ===
        "recording"
    ) {
      stopChallengeVideoRecording(
        true
      );
    } else {
      releaseAnalysisCameraStream();
    }

    revokeSessionVideoUrl();

    sessionQuestionMarks = [];
    sessionVideoMode = null;
    sessionVideoStartedAtPerf = null;
    sessionVideoStartedAtIso = null;
    sessionVideoDurationMs = 0;

    videoReviewPanel.classList.add(
      "hidden"
    );
  }

  function requestStartMode(...args) {
    return appDiagnostics.measure("requestStartMode", () => requestStartModeMeasured.apply(this,args));
  }
  function requestStartModeMeasured(
    mode,
    sourceButton = null
  ) {
    // 動画での振り返りは現在非表示・停止。
    analysisVideoEnabled = false;
    resetSessionVideoData();
    startMode(mode);
  }

  function beginRecordedChallenge() {
    const mode =
      pendingVideoMode;

    if (
      !mode ||
      !analysisCameraStream
    ) {
      return;
    }

    const started =
      startChallengeVideoRecording(
        mode
      );

    if (!started) {
      cameraSetupStatus.textContent =
        "録画を開始できませんでした。『撮影なしで開始』を選んでください。";
      return;
    }

    pendingVideoMode = null;

    closeCameraSetup(
      false
    );

    startMode(
      mode
    );
  }

  function beginChallengeWithoutVideo() {
    const mode =
      pendingVideoMode;

    if (!mode) {
      closeCameraSetup(true);
      return;
    }

    pendingVideoMode = null;

    closeCameraSetup(
      true
    );

    resetSessionVideoData();

    startMode(
      mode
    );
  }

  function getVideoQuestionMark(
    questionIndex
  ) {
    return (
      sessionQuestionMarks[
        questionIndex
      ] ||
      null
    );
  }

  function recordVideoQuestionStart(
    questionIndex,
    q
  ) {
    if (
      !sessionVideoActive ||
      !q
    ) {
      return;
    }

    let mark =
      getVideoQuestionMark(
        questionIndex
      );

    if (!mark) {
      mark = {
        index:
          questionIndex,
        mode:
          currentMode,
        formula:
          questionFormula(q),
        expected:
          q.answer,
        isWeakness:
          Boolean(
            q.isWeakness
          ),
        startMs: null,
        answerMs: null,
        endMs: null,
        user: null,
        ok: null,
        hintUsed: false,
        hintCount: 0
      };

      sessionQuestionMarks[
        questionIndex
      ] = mark;
    }

    if (
      mark.startMs === null
    ) {
      mark.startMs =
        videoElapsedMs();
    }
  }

  function recordVideoQuestionAnswer(
    questionIndex,
    user,
    ok
  ) {
    if (
      sessionVideoStartedAtPerf ===
      null
    ) {
      return;
    }

    const q =
      questions[
        questionIndex
      ];

    if (!q) {
      return;
    }

    recordVideoQuestionStart(
      questionIndex,
      q
    );

    const mark =
      getVideoQuestionMark(
        questionIndex
      );

    if (!mark) {
      return;
    }

    const now =
      videoElapsedMs();

    mark.answerMs =
      now;

    mark.endMs =
      now;

    mark.user =
      user;

    mark.ok =
      Boolean(ok);
  }

  function recordVideoHintUse(
    questionIndex
  ) {
    if (
      sessionVideoStartedAtPerf ===
      null
    ) {
      return;
    }

    const q =
      questions[
        questionIndex
      ];

    if (!q) {
      return;
    }

    recordVideoQuestionStart(
      questionIndex,
      q
    );

    const mark =
      getVideoQuestionMark(
        questionIndex
      );

    if (!mark) {
      return;
    }

    mark.hintUsed = true;
    mark.hintCount += 1;
  }

  function finalizeVideoQuestionMarks() {
    if (
      sessionVideoStartedAtPerf ===
      null
    ) {
      return;
    }

    const now =
      videoElapsedMs();

    sessionVideoDurationMs =
      now || 0;

    sessionQuestionMarks.forEach(
      (mark) => {
        if (
          mark &&
          mark.endMs === null
        ) {
          mark.endMs =
            now;
        }
      }
    );
  }

  function formatVideoSeconds(
    ms
  ) {
    if (
      ms === null ||
      ms === undefined ||
      !Number.isFinite(
        Number(ms)
      )
    ) {
      return "-";
    }

    return (
      Number(ms) / 1000
    ).toFixed(1) + "秒";
  }

  function medianNumber(
    values
  ) {
    if (!values.length) {
      return 0;
    }

    const sorted =
      values
        .slice()
        .sort(
          (a, b) =>
            a - b
        );

    const mid =
      Math.floor(
        sorted.length / 2
      );

    if (
      sorted.length % 2
    ) {
      return sorted[mid];
    }

    return (
      sorted[mid - 1] +
      sorted[mid]
    ) / 2;
  }

  function buildCurrentSessionRecord(
    challengeScore,
    timeup
  ) {
    const questionsForLog =
      answers.map((entry, i) => {
        const timing =
          questionTimingLog[i] || {};

        const videoMark =
          sessionQuestionMarks[i] || {};

        const skillId =
          skillForQuestion(
            entry.q
          );

        return {
          index: i,
          a: entry.q.a,
          b: entry.q.b,
          op: entry.q.op,
          terms: questionTerms(entry.q),
          operators: questionOperators(entry.q),
          formula: questionFormula(entry.q, false),
          answer: entry.q.answer,
          user: entry.user,
          ok: Boolean(entry.ok),
          skillId,
          isWeakness:
            Boolean(
              entry.q.isWeakness
            ),
          responseMs:
            Number(
              timing.responseMs ??
              (
                videoMark.answerMs !== undefined &&
                videoMark.startMs !== undefined &&
                videoMark.answerMs !== null &&
                videoMark.startMs !== null
                  ? videoMark.answerMs -
                    videoMark.startMs
                  : 0
              )
            ) || 0,
          hintUsed:
            (Number(timing.hintCount) || 0) > 0 ||
            Boolean(videoMark.hintUsed),
          outcome:
            (
              (Number(timing.hintCount) || 0) > 0 ||
              Boolean(videoMark.hintUsed)
            )
              ? "hint"
              : entry.ok
                ? "correct"
                : "wrong",
          hintCount:
            Math.max(
              Number(timing.hintCount) || 0,
              Number(videoMark.hintCount) || 0
            ),
          hintQuestionAttempts:
            Number(
              timing.hintQuestionAttempts
            ) || 0,
          hintQuestionCorrectCount:
            Number(
              timing.hintQuestionCorrectCount
            ) || 0,
          hintQuestionWrongCount:
            Number(
              timing.hintQuestionWrongCount
            ) || 0,
          points:
            questionPointsForAnswer(
              entry,
              i
            )
        };
      });

    const record = {
      id:
        `${Date.now()}-` +
        Math.random()
          .toString(36)
          .slice(2, 9),
      finishedAt:
        new Date().toISOString(),
      mode:
        currentMode,
      modeTitle:
        activeRemedialSkillId
          ? `補習｜${SKILL_DEFS[activeRemedialSkillId]?.title || ""}`
          : activeWeaknessChallengeMode
            ? `苦手克服｜${shortModeName(currentMode)}`
            : modeInfo[currentMode]?.title,
      remedialSkillId:
        activeRemedialSkillId,
      weaknessChallengeMode:
        activeWeaknessChallengeMode,
      timeup:
        Boolean(timeup),
      certificationEligible:
        !activeRemedialSkillId &&
        !activeWeaknessChallengeMode,
      timeLimitEnabled: true,
      completedWithinLimit:
        Boolean(!timeup),
      correctCount:
        Number(
          challengeScore?.correctCount
        ) || 0,
      hintCount:
        Number(
          challengeScore?.hintCount
        ) || 0,
      wrongCount:
        Number(
          challengeScore?.wrongCount
        ) || 0,
      totalQuestions:
        sessionTotalQuestions,
      maxStreak:
        Number(maxCorrectStreak) || 0,
      finalScore:
        Number(
          challengeScore?.finalScore
        ) || 0,
      videoUsed:
        sessionVideoStartedAtPerf !==
          null,
      videoDurationMs:
        Number(
          sessionVideoDurationMs
        ) || 0,
      questions:
        questionsForLog,
      issues: []
    };

    record.issues =
      analyzeSessionIssues(record);

    return record;
  }

  function medianPositive(values) {
    const clean = values
      .map(Number)
      .filter(
        (value) =>
          Number.isFinite(value) &&
          value > 0
      )
      .sort(
        (a, b) => a - b
      );

    if (!clean.length) {
      return 0;
    }

    const mid =
      Math.floor(clean.length / 2);

    return clean.length % 2
      ? clean[mid]
      : (
          clean[mid - 1] +
          clean[mid]
        ) / 2;
  }

  function analyzeSessionIssues(
    record
  ) {
    const responseTimes =
      (record.questions || [])
        .map((q) => q.responseMs)
        .filter((ms) => ms > 0);

    const medianMs =
      medianPositive(
        responseTimes
      );

    const slowThreshold =
      Math.max(
        7000,
        medianMs > 0
          ? medianMs * 1.45
          : 7000
      );

    const bySkill = {};

    (record.questions || [])
      .forEach((question) => {
        const skillId =
          question.skillId ||
          skillForQuestion(question);

        if (!bySkill[skillId]) {
          bySkill[skillId] = {
            skillId,
            count: 0,
            wrong: 0,
            slow: 0,
            hints: 0,
            score: 0,
            examples: []
          };
        }

        const item =
          bySkill[skillId];

        item.count += 1;

        if (!question.ok) {
          item.wrong += 1;
          item.score += 3;
        }

        if (question.hintUsed) {
          item.hints += 1;
          item.score += 2;
        }

        if (
          question.responseMs >
          slowThreshold
        ) {
          item.slow += 1;
          item.score += 1;
        }

        if (
          !question.ok ||
          question.hintUsed ||
          question.responseMs >
            slowThreshold
        ) {
          if (item.examples.length < 2) {
            item.examples.push(
              question.formula ||
              questionFormula(question, false)
            );
          }
        }
      });

    const issues =
      Object.values(bySkill)
        .filter((item) => item.score > 0)
        .sort(
          (a, b) =>
            b.score - a.score
        )
        .slice(0, 3)
        .map((item) => {
          const def =
            SKILL_DEFS[item.skillId];

          const reasons = [];

          if (item.wrong > 0) {
            reasons.push(
              `間違い${item.wrong}問`
            );
          }

          if (item.slow > 0) {
            reasons.push(
              `時間が長い${item.slow}問`
            );
          }

          if (item.hints > 0) {
            reasons.push(
              `ヒント使用${item.hints}問`
            );
          }

          const examples =
            item.examples.length
              ? `（${item.examples.join("、")}）`
              : "";

          return {
            skillId:
              item.skillId,
            title:
              def?.shortIssue ||
              def?.title ||
              "計算の考え方を復習",
            evidence:
              `${reasons.join("・")}${examples}`,
            explanation:
              def?.explanation ||
              "同じ種類の問題をゆっくり確認してから、補習問題で定着を確認します。"
          };
        });

    if (!issues.length) {
      return [{
        skillId: null,
        title:
          "今回は大きなつまずきなし",
        evidence:
          "正誤・回答時間・ヒント利用のログでは、大きな課題は見つかりませんでした。",
        explanation:
          "同じ考え方を別の数字でも安定して使えるか、次回も確認します。"
      }];
    }

    return issues;
  }

  function saveCompletedSession(
    record
  ) {
    if (
      sessionHistorySaved ||
      !record
    ) {
      return;
    }

    sessionHistory.push(record);
    sessionHistory = sessionHistory
      .slice(-MAX_SESSION_HISTORY);

    saveSessionHistory();

    updateRankCertificationState(
      record
    );

    const newlyEarned =
      syncEarnedMedalsFromEvidence(
        record.finishedAt
      );

    sessionHistorySaved = true;
    updateRankUi();
    renderWeaknessChallengeGrid();
    renderChallengeResumeCard();

    if (newlyEarned.length) {
      const activeTrackKey =
        trackKeyForMode(record.mode);

      const candidates = activeTrackKey
        ? newlyEarned.filter(
            (award) =>
              award.trackKey === activeTrackKey
          )
        : newlyEarned;

      const pool = candidates.length
        ? candidates
        : newlyEarned;

      const highestAward =
        [...pool].sort((a, b) => {
          const ruleA = ruleForId(a.rankId);
          const ruleB = ruleForId(b.rankId);

          return (
            (ruleA?.index ?? -1) -
            (ruleB?.index ?? -1)
          ) || (
            MEDAL_TIER_ORDER[a.tierKey] -
            MEDAL_TIER_ORDER[b.tierKey]
          );
        }).pop();

      if (highestAward) {
        setTimeout(
          () => {
            showRankCelebration(
              highestAward.rankId,
              highestAward.tierKey,
              newlyEarned
            );
          },
          900
        );
      }
    }
  }

  function renderPostSessionCoaching(
    record = null
  ) {
    const target =
      record ||
      sessionHistory[
        sessionHistory.length - 1
      ] ||
      null;

    if (!target) {
      videoReviewPanel.classList.add(
        "hidden"
      );
      return;
    }

    videoReviewPanel.classList.remove(
      "hidden"
    );

    updateRankUi();

    coachingIssueList.innerHTML = "";

    (target.issues || [])
      .forEach((issue) => {
        const card =
          document.createElement(
            "div"
          );

        card.className =
          "coaching-issue-card";

        const title =
          document.createElement(
            "div"
          );

        title.className =
          "coaching-issue-title";

        title.textContent =
          `課題：${issue.title}`;

        const evidence =
          document.createElement(
            "div"
          );

        evidence.className =
          "coaching-issue-evidence";

        evidence.textContent =
          issue.evidence || "";

        const explain =
          document.createElement(
            "div"
          );

        explain.className =
          "coaching-issue-explain";

        explain.textContent =
          issue.explanation || "";

        card.appendChild(title);
        card.appendChild(evidence);
        card.appendChild(explain);

        if (
          issue.skillId &&
          SKILL_DEFS[issue.skillId]
        ) {
          const actions =
            document.createElement(
              "div"
            );

          actions.className =
            "coaching-issue-actions";

          const lessonButton =
            document.createElement(
              "button"
            );

          lessonButton.type =
            "button";

          lessonButton.textContent =
            "解説を見る";

          lessonButton.addEventListener(
            "click",
            () => {
              openSkillLesson(
                issue.skillId
              );
            }
          );

          const practiceButton =
            document.createElement(
              "button"
            );

          practiceButton.type =
            "button";

          practiceButton.className =
            "primary";

          practiceButton.textContent =
            "補習問題をやる";

          practiceButton.addEventListener(
            "click",
            () => {
              startRemedialPractice(
                issue.skillId
              );
            }
          );

          actions.appendChild(
            lessonButton
          );

          actions.appendChild(
            practiceButton
          );

          card.appendChild(
            actions
          );
        }

        coachingIssueList.appendChild(
          card
        );
      });

    videoReviewStatus.textContent =
      target.videoUsed
        ? "学習ログは端末内へ自動保存済みです。録画動画は必要な場合だけ保存できます。"
        : "学習ログは端末内へ自動保存済みです。";

    $("#downloadSessionVideoBtn").disabled =
      !sessionVideoUrl;

    $("#downloadSessionLogBtn").disabled =
      false;
  }

  function renderVideoReviewPanel() {
    renderPostSessionCoaching();
  }

  function downloadSessionVideo() {
    if (
      !sessionVideoUrl ||
      !sessionVideoBlob
    ) {
      return;
    }

    const extension =
      sessionVideoMimeType
        .includes("mp4")
        ? "mp4"
        : "webm";

    const link =
      document.createElement(
        "a"
      );

    link.href =
      sessionVideoUrl;

    link.download =
      `soroban_${sessionVideoMode || "challenge"}_${Date.now()}.${extension}`;

    document.body.appendChild(
      link
    );

    link.click();
    link.remove();
  }

  function downloadSessionLog() {
    const payload =
      sessionHistory[
        sessionHistory.length - 1
      ] || {
        appVersion:
          APP_VERSION,
        mode:
          currentMode,
        questions: []
      };

    const blob =
      new Blob(
        [
          JSON.stringify(
            payload,
            null,
            2
          )
        ],
        {
          type:
            "application/json"
        }
      );

    const url =
      URL.createObjectURL(
        blob
      );

    const link =
      document.createElement(
        "a"
      );

    link.href = url;
    link.download =
      `soroban_analysis_${payload.mode || "challenge"}_${Date.now()}.json`;

    document.body.appendChild(
      link
    );

    link.click();
    link.remove();

    setTimeout(
      () => {
        URL.revokeObjectURL(url);
      },
      1000
    );
  }


  function toggleTimeLimit() {
    timeDisplayEnabled =
      !timeDisplayEnabled;

    saveTimeDisplaySetting();
    updateTimeLimitUi();
  }

  function resetChallengeScrollPosition(target = workspace, isActive = null) {
    const reset = () => {
      if (isActive && !isActive()) return;
      try {
        window.scrollTo({
          top: 0,
          left: 0,
          behavior: "auto"
        });
      } catch (error) {
        try {
          window.scrollTo(0, 0);
        } catch (innerError) {}
      }

      try {
        document.documentElement.scrollTop = 0;
        document.body.scrollTop = 0;
      } catch (error) {}

      // Streamlit側を操作できる環境では外側の位置も戻す。
      try {
        if (
          window.parent &&
          window.parent !== window
        ) {
          window.parent.scrollTo({
            top: 0,
            left: 0,
            behavior: "auto"
          });
        }
      } catch (error) {}

      try {
        target.scrollIntoView({
          block: "start",
          inline: "nearest",
          behavior: "auto"
        });
      } catch (error) {}
    };

    // 表示切替直後にも即時で最上部へ戻す。
    reset();

    requestAnimationFrame(() => {
      requestAnimationFrame(
        reset
      );
    });

    // 表示切替で高さが確定した後にも合わせる。
    setTimeout(
      reset,
      120
    );
  }

  function restartCurrentChallengeFromBeginning() {
    if (
      !currentMode ||
      !workspace.classList.contains(
        "show"
      ) ||
      results.classList.contains(
        "show"
      )
    ) {
      return;
    }

    const mode =
      currentMode;
    const sameQuestions =
      Array.isArray(questions)
        ? questions.map(
            (question) => ({
              ...question
            })
          )
        : [];

    const wasWeakness =
      activeWeaknessChallengeMode;
    const wasRemedial =
      activeRemedialSkillId;
    const voiceWasOn =
      voiceAnswerEnabled;
    const total =
      sessionTotalQuestions;

    clearChallengeResumeState();

    startMode(
      mode,
      {
        presetQuestions:
          sameQuestions,
        totalQuestions:
          total,
        weaknessChallengeMode:
          wasWeakness,
        remedialSkillId:
          wasRemedial,
        voiceAnswerEnabled:
          voiceWasOn
      }
    );
  }

  function startMode(
    mode,
    options = {}
  ) {
    scoreAnimationToken += 1;

    const resumeState =
      options.resumeState ||
      null;

    if (!resumeState) {
      clearChallengeResumeState();
    }

    bgmEngine.ensureContext();
    bgmEngine.ensureRunning();

    currentMode = mode;
    activeRemedialSkillId =
      resumeState?.activeRemedialSkillId ||
      options.remedialSkillId ||
      null;

    activeWeaknessChallengeMode =
      resumeState?.activeWeaknessChallengeMode ||
      options.weaknessChallengeMode ||
      null;

    const challengeMenuTarget =
      activeWeaknessChallengeMode
        ? "weakness"
        : "challenge-menu";

    const quitButton =
      $("#quitBtn");

    if (quitButton) {
      quitButton.dataset.appNav =
        challengeMenuTarget;
    }

    const resultMenuBtn =
      $("#menuBtn");
    if (resultMenuBtn) {
      resultMenuBtn.dataset.appNav =
        challengeMenuTarget;
    }

    sessionTotalQuestions =
      Math.max(
        1,
        Math.min(
          TOTAL_QUESTIONS,
          Number(
            resumeState?.sessionTotalQuestions ??
            options.totalQuestions ??
            TOTAL_QUESTIONS
          ) || TOTAL_QUESTIONS
        )
      );

    mainStampAttempt = beginSharedStamp("calculation", modeInfo[mode]?.title || String(mode),sessionTotalQuestions,resumeState?.stampAttempt);
    learningMenu(mainStampAttempt,`soroban:calculation:${mode}`,"soroban:"+(MODE_GROUPS.find(g=>g.modes.includes(mode))?.key||"advanced"),1);
    if(mainStampAttempt)mainStampAttempt.assignment_context={remedial_skill_id:activeRemedialSkillId,weakness_mode:activeWeaknessChallengeMode};
    if (resumeState && !resumeState.stampAttempt) {
      (resumeState.answers || []).forEach((entry,i) => recordSharedStampAnswer(mainStampAttempt,i,entry.ok && !entry.hintUsed));
    }
    questions =
      resumeState
        ? Array.isArray(
            resumeState.questions
          )
          ? resumeState.questions
          : []
        : Array.isArray(
            options.presetQuestions
          )
          ? options.presetQuestions.slice(
              0,
              sessionTotalQuestions
            )
          : [];

    questionTimingLog =
      resumeState &&
      Array.isArray(
        resumeState.questionTimingLog
      )
        ? resumeState.questionTimingLog.map(
            (item) =>
              item
                ? {
                    ...item,
                    startPerf: null
                  }
                : item
          )
        : [];

    sessionHistorySaved = false;

    if (
      !sessionVideoActive
    ) {
      sessionQuestionMarks = [];
      sessionVideoMode = null;
      sessionVideoStartedAtPerf = null;
      sessionVideoStartedAtIso = null;
      sessionVideoDurationMs = 0;
    }

    videoReviewPanel.classList.add(
      "hidden"
    );

    index =
      resumeState
        ? Math.max(
            0,
            Math.min(
              sessionTotalQuestions - 1,
              Number(
                resumeState.index
              ) || 0
            )
          )
        : 0;

    gowasanSpokenForIndex = -1;
    score =
      resumeState
        ? Number(
            resumeState.score
          ) || 0
        : 0;

    answers =
      resumeState &&
      Array.isArray(
        resumeState.answers
      )
        ? resumeState.answers
        : [];

    seconds =
      resumeState
        ? Math.max(
            0,
            Number(
              resumeState.seconds
            ) || 0
          )
        : 300;

    // 旧再開データが時間制限OFFでも、現在は常時5分計測。
    timeLimitEnabled = true;

    locked = false;
    correctStreak =
      resumeState
        ? Number(
            resumeState.correctStreak
          ) || 0
        : 0;

    maxCorrectStreak =
      resumeState
        ? Number(
            resumeState.maxCorrectStreak
          ) || 0
        : 0;

    currentBgm = null;
    currentBgmGroupKey = null;

    sessionWeakAsked =
      resumeState
        ? Number(
            resumeState.sessionWeakAsked
          ) || 0
        : 0;

    sessionWeakCorrect =
      resumeState
        ? Number(
            resumeState.sessionWeakCorrect
          ) || 0
        : 0;

    promotedMode = null;
    sessionRankingSaved = false;
    sessionChallengeRecorded = false;
    sessionChallengeMedalAwarded = false;
    sessionChallengeMedalTier = null;
    closeRankingModal();

    $("#retryBtn").textContent =
      "もう一回チャレンジ";

    if (promoteBtn) {
      promoteBtn.classList.add(
        "hidden"
      );
    }

    homeView.classList.add("hidden");
    learningView.classList.remove("show");
    anzanView.classList.remove("show");
    settingsView.classList.remove("show");
    weaknessView.classList.remove("show");
    menuView.classList.add("hidden");
    workspace.classList.add("show");
    resetChallengeScrollPosition();
    questionCard.classList.remove(
      "hidden",
      "voice-waiting"
    );
    results.classList.remove("show");

    $("#statusTitle").textContent =
      activeRemedialSkillId
        ? `補習｜${SKILL_DEFS[activeRemedialSkillId].title}`
        : activeWeaknessChallengeMode
          ? `苦手克服｜${shortModeName(mode)}`
          : modeInfo[mode].title;

    $("#streak").textContent =
      `連続正解 ${correctStreak}`;

    updateChallengeOutcomeDisplay();

    hintBtn.disabled =
      sessionVideoActive;

    hintBtn.classList.toggle(
      "recording-disabled",
      sessionVideoActive
    );

    hintBtn.textContent =
      sessionVideoActive
        ? "撮影中：終了後に復習"
        : "珠ヒントを見る（手動＋音声）";

    voiceAnswerEnabled =
      resumeState
        ? Boolean(
            resumeState.voiceAnswerEnabled
          )
        : options.voiceAnswerEnabled !== undefined
          ? Boolean(options.voiceAnswerEnabled)
          : preferredVoiceAnswerEnabled;

    updateVoiceUi(
      voiceAnswerEnabled
        ? "音声回答：開始します…"
        : "音声回答：OFF"
    );

    feedback.textContent = "";
    feedback.className = "feedback";

    updateStreakFrame(
      correctStreak
    );

    stopTimer();
    updateTimeLimitUi();
    updateTimer();

    timerHandle = setInterval(() => {
      seconds = Math.max(
        0,
        seconds - 1
      );
      updateTimer();

      if (!locked) {
        saveChallengeResumeState();
      }

      // 0:00になったら計測だけ止める。
      // チャレンジは強制終了せず、金メダル対象外になるだけ。
      if (seconds <= 0) {
        stopTimer();
      }
    }, 1000);

    if (activeRemedialSkillId) {
      statusSub.textContent =
        `補習問題${sessionTotalQuestions}問・5分計測`;
    } else if (
      activeWeaknessChallengeMode
    ) {
      statusSub.textContent =
        `間違えた問題${sessionTotalQuestions}問・5分計測`;
    }

    playBgmForStreak(0, true);
    renderQuestion();
    resetChallengeScrollPosition();

    if (resumeState) {
      saveChallengeResumeState();
    }
  }

  function renderQuestion(...args) {
    return appDiagnostics.measure("renderQuestion", () => renderQuestionMeasured.apply(this,args));
  }
  function renderQuestionMeasured(voiceReady = false) {
    hideSorobanHint();

    // 音声モードでは、
    // 「ゴワサン！」→マイクonstart の前に問題を作らない。
    if (
      voiceAnswerEnabled &&
      !voiceReady
    ) {
      hideQuestionForVoiceCallout();

      // 前の問題が一瞬見えないように表示内容も消しておく。
      equation.textContent = "";
      equation.classList.remove(
        "multi-term",
        "long-sequence"
      );
      answerInput.value = "";
      feedback.textContent = "";
      feedback.className = "feedback";

      $("#qCount").textContent =
        `${index + 1} / ${sessionTotalQuestions}`;
      updateChallengeOutcomeDisplay();

      $("#weakBadge").classList.remove(
        "show"
      );

      bar.style.width =
        `${(index / sessionTotalQuestions) * 100}%`;

      // 前問の判定後は locked=true なので、
      // 次のゴワサン→マイク開始へ進めるようここで解除する。
      locked = false;

      if (!voicePauseForFeedback) {
        scheduleVoiceRestart(350);
      }

      return;
    }

    // 非音声モード、またはマイクonstart確認後だけ
    // ここで問題を生成する。
    if (!questions[index]) {
      questions[index] =
        makeQuestionForIndex(
          index,
          currentMode
        );
    }

    const q = questions[index];

    if (!isValidQuestion(q)) {
      throw new Error(
        `表示禁止問題を検出: ${questionFormula(q)}`
      );
    }

    $("#qCount").textContent =
      `${index + 1} / ${sessionTotalQuestions}`;

    updateChallengeOutcomeDisplay();

    $("#weakBadge").classList.toggle(
      "show",
      Boolean(q.isWeakness)
    );

    bar.style.width =
      `${(index / sessionTotalQuestions) * 100}%`;

    const formula = questionFormula(q);

    equation.textContent =
      `${formula} ＝ ?`;

    equation.classList.toggle(
      "multi-term",
      isMultiTermQuestion(q)
    );

    equation.classList.toggle(
      "long-sequence",
      formula.length >= 24
    );

    learningQuestion(mainStampAttempt,index,q);
    markQuestionDisplayed(
      index
    );

    recordVideoQuestionStart(
      index,
      q
    );

    answerInput.value = "";
    feedback.textContent = "";
    feedback.className = "feedback";
    locked = false;

    // ここへ voiceReady=true で来た時点では、
    // マイクはすでに聞き取り状態。
    cmEmit(mainStampAttempt,"learning_activity",{activity_type:"answer_acceptance_started",substep_id:null,result:null,observation_basis:"question_visible_and_input_unlocked"},mainStampAttempt?.questions[String(index)]);
    revealQuestionAfterVoiceCallout();

    // 10問連続正解以上では、
    // 問題が実際に表示された瞬間だけ発光。
    flashQuestionFrameIfNeeded();

    saveChallengeResumeState();
  }


  function challengeOutcomeCounts() {
    let correct = 0;
    let hint = 0;
    let wrong = 0;

    answers.forEach((entry) => {
      if (entry?.hintUsed) {
        hint += 1;
      } else if (entry?.ok) {
        correct += 1;
      } else {
        wrong += 1;
      }
    });

    return { correct, hint, wrong };
  }

  function updateChallengeOutcomeDisplay() {
    const counts =
      challengeOutcomeCounts();

    $("#score").textContent =
      `正解 ${counts.correct}｜珠ヒント ${counts.hint}`;
  }

  function submitAnswer() {
    if (
      locked ||
      index >= sessionTotalQuestions
    ) return;

    const raw =
      String(answerInput.value || "").trim();

    if (raw === "") {
      feedback.textContent =
        "答えを入力してください";
      feedback.className =
        "feedback bad";
      return;
    }

    const user = Number(raw);
    if (!Number.isFinite(user)) return;

    locked = true;

    const q = questions[index];
    const ok = user === q.answer;
    const timing =
      ensureQuestionTiming(index);
    const hintUsed =
      (Number(timing.hintCount) || 0) > 0;

    markQuestionAnswered(index);

    recordVideoQuestionAnswer(
      index,
      user,
      ok
    );

    recordAnswer(
      currentMode,
      q,
      ok,
      hintUsed
    );

    if (
      q.isWeakness &&
      ok &&
      !hintUsed
    ) {
      sessionWeakCorrect += 1;
    }

    if (hintUsed) {
      // 珠ヒント使用は正解・不正解ではなく独立区分。
      correctStreak = 0;
    } else if (ok) {
      score += 1;
      correctStreak += 1;
      maxCorrectStreak = Math.max(
        maxCorrectStreak,
        correctStreak
      );
    } else {
      correctStreak = 0;
    }

    const outcome =
      hintUsed
        ? "hint"
        : ok
          ? "correct"
          : "wrong";

    learningResponse(mainStampAttempt,index,ok,"answer",user);
    recordSharedStampAnswer(mainStampAttempt,index,ok && !hintUsed);
    answers.push({
      q,
      user,
      ok,
      hintUsed,
      outcome
    });

    updateChallengeOutcomeDisplay();
    $("#streak").textContent =
      `連続正解 ${correctStreak}`;

    updateStreakFrame(correctStreak);
    playBgmForStreak(correctStreak);

    if (
      index + 1 <
      sessionTotalQuestions
    ) {
      saveChallengeResumeState(
        index + 1
      );
    }

    if (hintUsed) {
      feedback.textContent = ok
        ? "珠ヒントとして記録しました。"
        : `珠ヒントとして記録しました。答えは ${q.answer}`;
      feedback.className =
        "feedback";
    } else {
      feedback.textContent = ok
        ? "お見事！"
        : `残念！ 答えは ${q.answer}`;
      feedback.className =
        `feedback ${ok ? "good" : "bad"}`;
    }

    if(!ok)cmSupport(mainStampAttempt,mainStampAttempt?.questions[String(index)],"answer",null,null,true);
    const advanceAfterFeedback = () => {
      setTimeout(() => {
        index += 1;

        if (
          index >=
          sessionTotalQuestions
        ) {
          finish(false);
        } else {
          renderQuestion();
        }
      }, 140);
    };

    speakAnswerFeedback(
      ok,
      correctStreak,
      advanceAfterFeedback,
      hintUsed
        ? "珠ヒントとして記録しました。"
        : null
    );
  }

  function updateTimer() {
    timerEl.classList.toggle(
      "hidden",
      !timeDisplayEnabled
    );

    const safe = Math.max(0, seconds);
    const min = Math.floor(safe / 60);
    const sec = safe % 60;

    timerEl.textContent =
      `${String(min).padStart(2, "0")}:` +
      `${String(sec).padStart(2, "0")}`;

    timerEl.classList.toggle(
      "warn",
      seconds <= 60
    );
  }

  function stopTimer() {
    if (timerHandle) {
      clearInterval(timerHandle);
      timerHandle = null;
    }
  }

  function calculateChallengeScore() {
    const outcomeCounts =
      challengeOutcomeCounts();

    const wrongCount =
      outcomeCounts.wrong;
    const hintCount =
      outcomeCounts.hint;

    const remainingSeconds =
      Math.max(0, seconds);

    const remainingMinutes =
      remainingSeconds / 60;

    const questionPoints =
      answers.map(
        (entry, questionIndex) =>
          questionPointsForAnswer(
            entry,
            questionIndex
          )
      );

    const fivePointCorrect =
      questionPoints.filter(
        (points) => points === 5
      ).length;

    const fourPointCorrect =
      questionPoints.filter(
        (points) => points === 4
      ).length;

    const threePointCorrect =
      questionPoints.filter(
        (points) => points === 3
      ).length;

    // 点数は従来どおり3〜5点方式を維持する。
    // ただしチャレンジ成績・メダル判定では、
    // 珠ヒント使用問題は「正解」「不正解」のどちらにも入れない。
    const finalScore =
      questionPoints.reduce(
        (sum, points) =>
          sum + points,
        0
      );

    return {
      correctCount:
        outcomeCounts.correct,
      hintCount,
      totalQuestions:
        sessionTotalQuestions,
      maxStreak: maxCorrectStreak,
      remainingSeconds,
      remainingMinutes,
      wrongCount,
      questionPoints,
      fivePointCorrect,
      fourPointCorrect,
      threePointCorrect,
      rawScore: finalScore,
      finalScore
    };
  }

  function playBabaanSound() {
    try {
      const AudioContextClass =
        window.AudioContext ||
        window.webkitAudioContext;

      if (!AudioContextClass) {
        return;
      }

      const ctx = new AudioContextClass();
      const now = ctx.currentTime;

      const master = ctx.createGain();
      master.gain.setValueAtTime(0.0001, now);
      master.gain.exponentialRampToValueAtTime(
        0.92,
        now + 0.025
      );
      master.gain.exponentialRampToValueAtTime(
        0.0001,
        now + 1.05
      );
      const appVolumeOutput = connectAppAudioOutput(ctx, master);

      const notes = [
        { freq: 196.00, start: 0.00, dur: .78 },
        { freq: 261.63, start: 0.07, dur: .82 },
        { freq: 329.63, start: 0.14, dur: .90 },
        { freq: 523.25, start: 0.25, dur: .74 }
      ];

      notes.forEach((note, index) => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();

        osc.type =
          index === notes.length - 1
            ? "triangle"
            : "sawtooth";

        osc.frequency.setValueAtTime(
          note.freq,
          now + note.start
        );

        gain.gain.setValueAtTime(
          0.0001,
          now + note.start
        );
        gain.gain.exponentialRampToValueAtTime(
          index === notes.length - 1 ? .34 : .20,
          now + note.start + .025
        );
        gain.gain.exponentialRampToValueAtTime(
          0.0001,
          now + note.start + note.dur
        );

        osc.connect(gain);
        gain.connect(master);

        osc.start(now + note.start);
        osc.stop(now + note.start + note.dur + .04);
      });

      const drum = ctx.createOscillator();
      const drumGain = ctx.createGain();

      drum.type = "sine";
      drum.frequency.setValueAtTime(120, now);
      drum.frequency.exponentialRampToValueAtTime(
        46,
        now + .42
      );

      drumGain.gain.setValueAtTime(.44, now);
      drumGain.gain.exponentialRampToValueAtTime(
        .0001,
        now + .48
      );

      drum.connect(drumGain);
      drumGain.connect(master);

      drum.start(now);
      drum.stop(now + .5);

      setTimeout(() => {
        releaseAppAudioOutput(appVolumeOutput);
        ctx.close().catch(() => {});
      }, 1400);
    } catch (error) {
      // 効果音に失敗しても得点表示は続行する。
    }
  }

  function launchConfetti() {
    scoreStage
      .querySelectorAll(".confetti-piece")
      .forEach((node) => node.remove());

    const hues = [
      8, 32, 52, 105, 175, 210, 260, 315
    ];

    for (let i = 0; i < 42; i += 1) {
      const piece = document.createElement("span");
      piece.className = "confetti-piece";

      piece.style.left =
        `${Math.random() * 100}%`;

      piece.style.background =
        `hsl(${hues[i % hues.length]} 90% 58%)`;

      piece.style.setProperty(
        "--drift",
        `${-90 + Math.random() * 180}px`
      );

      piece.style.setProperty(
        "--spin",
        `${360 + Math.floor(Math.random() * 720)}deg`
      );

      piece.style.animationDelay =
        `${Math.random() * .16}s`;

      scoreStage.appendChild(piece);
    }

    setTimeout(() => {
      scoreStage
        .querySelectorAll(".confetti-piece")
        .forEach((node) => node.remove());
    }, 2200);
  }

  function speakFinalScore(scoreInfo) {
    if (
      !("speechSynthesis" in window) ||
      typeof SpeechSynthesisUtterance === "undefined"
    ) {
      return;
    }

    cancelAppSpeech();

    const points =
      scoreInfo.finalScore;

    const challengeCount =
      Math.max(
        0,
        Number(
          scoreInfo.challengeCount
        ) || 0
      );

    const challengeMessage =
      (
        challengeCount > 0 &&
        challengeCount % 5 === 0
      )
        ? `今回で${modeVoiceName(scoreInfo.mode)}モードは${challengeCount}回目のチャレンジでした。がんばってますね。`
        : null;

    let openingMessage = null;

    if (
      scoreInfo.correctCount === scoreInfo.totalQuestions &&
      scoreInfo.wrongCount === 0
    ) {
      openingMessage =
        "お見事！パーフェクト！";
    } else if (
      scoreInfo.correctCount === scoreInfo.totalQuestions - 1 &&
      scoreInfo.wrongCount === 1
    ) {
      openingMessage =
        "惜しい！もう少しでパーフェクト！";
    }

    const makeUtterance = (
      message,
      rate = 0.96,
      pitch = 1.03
    ) => {
      const utterance =
        new SpeechSynthesisUtterance(
          message
        );

      utterance.lang = "ja-JP";
      utterance.rate = rate;
      utterance.pitch = pitch;
      utterance.volume = appMasterVolume;

      const voice =
        getJapaneseVoice();

      if (voice) {
        utterance.voice = voice;
      }

      return utterance;
    };

    const speakChallengeMessage = () => {
      if (!challengeMessage) {
        return;
      }

      const challengeUtterance =
        makeUtterance(
          challengeMessage,
          0.95,
          1.02
        );

      speakWithAppVolume(
        challengeUtterance
      );
    };

    const speakPoints = () => {
      const scoreUtterance =
        makeUtterance(
          `得点は、${points}点！`,
          0.98,
          1.04
        );

      if (challengeMessage) {
        let continued = false;

        const continueToChallenge = () => {
          if (continued) {
            return;
          }

          continued = true;

          setTimeout(() => {
            speakChallengeMessage();
          }, 260);
        };

        scoreUtterance.onend =
          continueToChallenge;

        scoreUtterance.onerror =
          continueToChallenge;
      }

      speakWithAppVolume(
        scoreUtterance
      );
    };

    if (openingMessage) {
      const openingUtterance =
        makeUtterance(
          openingMessage,
          0.96,
          1.03
        );

      let continued = false;

      const continueToScore = () => {
        if (continued) {
          return;
        }

        continued = true;

        setTimeout(() => {
          speakPoints();
        }, 220);
      };

      openingUtterance.onend =
        continueToScore;

      openingUtterance.onerror =
        continueToScore;

      speakWithAppVolume(
        openingUtterance
      );

      return;
    }

    speakPoints();
  }

  function speakUntimedFinish(scoreInfo) {
    if (
      !("speechSynthesis" in window) ||
      typeof SpeechSynthesisUtterance === "undefined"
    ) {
      return;
    }

    const messages = [];

    if (
      scoreInfo.correctCount === scoreInfo.totalQuestions &&
      scoreInfo.wrongCount === 0
    ) {
      messages.push(
        "お見事！パーフェクト！"
      );
    } else if (
      scoreInfo.correctCount === scoreInfo.totalQuestions - 1 &&
      scoreInfo.wrongCount === 1
    ) {
      messages.push(
        "惜しい！もう少しでパーフェクト！"
      );
    }

    if (
      scoreInfo.challengeCount > 0 &&
      scoreInfo.challengeCount % 5 === 0
    ) {
      messages.push(
        `今回で${modeVoiceName(scoreInfo.mode)}モードは${scoreInfo.challengeCount}回目のチャレンジでした。がんばってますね。`
      );
    }

    if (messages.length === 0) {
      return;
    }

    cancelAppSpeech();

    const speakAt = (index) => {
      if (index >= messages.length) {
        return;
      }

      const utterance =
        new SpeechSynthesisUtterance(
          messages[index]
        );

      utterance.lang = "ja-JP";
      utterance.rate = 0.96;
      utterance.pitch = 1.03;
      utterance.volume = appMasterVolume;

      const voice =
        getJapaneseVoice();

      if (voice) {
        utterance.voice = voice;
      }

      utterance.onend = () => {
        setTimeout(() => {
          speakAt(index + 1);
        }, 220);
      };

      utterance.onerror =
        utterance.onend;

      speakWithAppVolume(
        utterance
      );
    };

    speakAt(0);
  }

  function runScoreRoulette(scoreInfo) {
    scoreAnimationToken += 1;
    const token = scoreAnimationToken;

    const finalPoints = scoreInfo.finalScore;

    scoreStage.classList.remove(
      "babaan",
      "score-rainbow"
    );

    if (finalPoints > 1000) {
      scoreStage.classList.add(
        "score-rainbow"
      );
    }
    resultScore.classList.remove("reveal");
    resultScore.classList.add("roulette");

    scoreFormula.textContent =
      `ヒントなし ${scoreInfo.fivePointCorrect}問×5点 ＋ ` +
      `珠ヒント使用・問いミスなし ${scoreInfo.fourPointCorrect}問×4点 ＋ ` +
      `珠ヒント内の問いでミス後正解 ${scoreInfo.threePointCorrect}問×3点`;

    let tick = 0;

    const rouletteTimer = setInterval(() => {
      if (token !== scoreAnimationToken) {
        clearInterval(rouletteTimer);
        return;
      }

      const spread = Math.max(
        finalPoints * 1.9,
        180
      );

      const randomValue = Math.max(
        0,
        Math.floor(Math.random() * spread)
      );

      resultScore.textContent =
        `${randomValue.toLocaleString()} 点`;

      tick += 1;
    }, 72);

    setTimeout(() => {
      if (token !== scoreAnimationToken) {
        clearInterval(rouletteTimer);
        return;
      }

      clearInterval(rouletteTimer);

      resultScore.classList.remove("roulette");
      resultScore.textContent =
        `${finalPoints.toLocaleString()} 点`;

      // 再アニメーションのためreflow
      void resultScore.offsetWidth;

      resultScore.classList.add("reveal");
      scoreStage.classList.add("babaan");

      playBabaanSound();
      launchConfetti();

      setTimeout(() => {
        if (token === scoreAnimationToken) {
          speakFinalScore(scoreInfo);
        }
      }, 380);

      setTimeout(() => {
        scoreStage.classList.remove("babaan", "score-rainbow");
      }, 900);
    }, 2700);
  }

  function finish(timeup) {
    // 5分を超えても最後まで解く。timeupは「時間超過」の記録だけに使う。
    timeup =
      Boolean(
        timeup ||
        seconds <= 0
      );

    clearChallengeResumeState();
    finalizeVideoQuestionMarks();

    if (
      sessionVideoStartedAtPerf !==
      null
    ) {
      stopChallengeVideoRecording(
        false
      );
    }

    stopTimer();
    stopBgm();
    hideSorobanHint();
    stopVoiceRecognition();

    if (
      timeup &&
      "speechSynthesis" in window
    ) {
      cancelAppSpeech();
    }

    locked = true;


    questionCard.classList.remove(
      "voice-waiting"
    );

    questionCard.classList.add(
      "hidden"
    );

    results.classList.add("show");

    $("#retryBtn").textContent =
      "もう一回チャレンジ";

    if (promoteBtn) {
      promoteBtn.classList.add(
        "hidden"
      );
    }

    const challengeScore =
      calculateChallengeScore();

    const earnedChallengeMedal = awardChallengeMedal(challengeScore, timeup);

    if (
      activeRemedialSkillId ||
      activeWeaknessChallengeMode
    ) {
      challengeScore.challengeCount =
        getChallengeCount(
          currentMode
        );

      challengeScore.mode =
        currentMode;
    } else if (!sessionChallengeRecorded) {
      challengeScore.challengeCount =
        incrementChallengeCount(
          currentMode
        );

      challengeScore.mode =
        currentMode;

      sessionChallengeRecorded = true;
    } else {
      challengeScore.challengeCount =
        getChallengeCount(
          currentMode
        );

      challengeScore.mode =
        currentMode;
    }

    const timedResult =
      !activeRemedialSkillId &&
      !activeWeaknessChallengeMode;

    scoreStage.classList.toggle(
      "hidden",
      !timedResult
    );

    resultRankingPanel.classList.toggle(
      "hidden",
      !timedResult
    );

    if (timedResult) {
      resultScore.textContent = "---";

      resultScore.classList.remove(
        "roulette",
        "reveal"
      );

      scoreStage.classList.remove(
        "babaan"
      );

      if (!sessionRankingSaved) {
        addScoreRanking(
          currentMode,
          challengeScore,
          timeup
        );

        sessionRankingSaved = true;
      }

      renderResultRanking(
        currentMode
      );
    }

    const weakSummary =
      sessionWeakAsked > 0
        ? `苦手克服 ${sessionWeakCorrect}/${sessionWeakAsked}問。`
        : "今回は苦手克服問題なし。";

    const outcomeSummary =
      `正解${challengeScore.correctCount}問・` +
      `珠ヒント${challengeScore.hintCount}問・` +
      `不正解${challengeScore.wrongCount}問`;

    const canPromote =
      !activeRemedialSkillId &&
      !activeWeaknessChallengeMode &&
      Boolean(
        NEXT_MODE[currentMode]
      ) &&
      shouldLevelUp(
        currentMode,
        score
      );

    promotedMode =
      canPromote
        ? NEXT_MODE[currentMode]
        : null;

    let resultMessage;

    if (activeRemedialSkillId) {
      resultMessage =
        `補習${sessionTotalQuestions}問終了。${outcomeSummary}です。`;
    } else if (activeWeaknessChallengeMode) {
      const remainingWeak =
        getWeakCandidates(
          currentMode
        ).length;

      resultMessage =
        `苦手克服${sessionTotalQuestions}問終了。${outcomeSummary}です。未克服は残り${remainingWeak}問です。`;
    } else if (timeup) {
      resultMessage =
        `${sessionTotalQuestions}問終了。5分を超えたため今回は金メダル条件の対象外です。${outcomeSummary}です。${weakSummary}`;
    } else {
      resultMessage =
        `${sessionTotalQuestions}問終了。5分以内に完了しました。残り時間は${timerEl.textContent}、${outcomeSummary}です。${weakSummary}`;
    }

    if (
      !activeRemedialSkillId &&
      !activeWeaknessChallengeMode
    ) {
      resultMessage +=
        ` 総チャレンジ回数は${challengeScore.challengeCount}回です。`;
    }

    if (promotedMode) {
      resultMessage +=
        ` 苦手を克服できたので、次は「${modeInfo[promotedMode].title}」へレベルアップします。`;

      if (promoteBtn) {
        promoteBtn.textContent =
          `次のレベルへ｜${shortModeName(promotedMode)}`;
        promoteBtn.classList.remove(
          "hidden"
        );
      }
    } else if (
      sessionWeakAsked > 0
    ) {
      resultMessage +=
        " 苦手は次回も優先して出題します。";
    }

    if (earnedChallengeMedal) {
      const label = getMedalTierDefinition(earnedChallengeMedal).label;
      const count = challengeMedalCount(currentMode, earnedChallengeMedal);
      resultMessage += ` ${label}メダルを1枚獲得しました（累計${count}枚）。`;
    }

    $("#resultNote").textContent =
      resultMessage;

    const review = $("#review");
    review.innerHTML = "";

    answers.forEach(
      (entry, i) => {
        const div =
          document.createElement(
            "div"
          );

        const entryHintUsed =
          Boolean(entry.hintUsed);

        div.className =
          `review-item ${
            entryHintUsed
              ? "hint"
              : entry.ok
                ? "correct"
                : "wrong"
          }`;

        const weakMark =
          entry.q.isWeakness
            ? "【苦手克服】"
            : "";

        const outcomeLabel =
          entryHintUsed
            ? "珠ヒント"
            : entry.ok
              ? "正解"
              : "不正解";

        div.textContent =
          `${i + 1}. ${weakMark}${questionFormula(entry.q)}` +
          ` ＝ ${entry.q.answer}｜${outcomeLabel}｜` +
          (
            entry.user === null
              ? "未回答"
              : `回答 ${entry.user}`
          );

        review.appendChild(div);
      }
    );

    const sessionRecord =
      buildCurrentSessionRecord(
        challengeScore,
        timeup
      );

    if (answers.length === sessionTotalQuestions) completeSharedStamp(mainStampAttempt,earnedChallengeMedal||'white');
    saveCompletedSession(
      sessionRecord
    );

    renderPostSessionCoaching(
      sessionRecord
    );

    if (timedResult) {
      // 5分モードだけ得点を表示・読み上げる。
      setTimeout(() => {
        runScoreRoulette(
          challengeScore
        );
      }, 450);
    } else {
      // 時間制限OFFでは得点は表示・読み上げない。
      setTimeout(() => {
        speakUntimedFinish(
          challengeScore
        );
      }, 450);
    }
  }

  function challengeIsOnTop() {
    return (
      !workspace.classList.contains("show") &&
      !rankingModal.classList.contains("show")
    );
  }

  function pushInAppBackGuard() {
    try {
      window.history.pushState(
        {
          sorobanInApp: true,
          guard: Date.now()
        },
        "",
        window.location.href
      );
    } catch (error) {}
  }

  function installInAppBackGuard() {
    if (inAppBackGuardReady) {
      return;
    }

    inAppBackGuardReady = true;

    // 最初に1つアプリ内履歴を作っておく。
    pushInAppBackGuard();

    window.addEventListener(
      "popstate",
      () => {
        if (handlingBrowserBack) {
          return;
        }

        handlingBrowserBack = true;

        try {
          if (
            cameraSetupModal.classList.contains(
              "show"
            )
          ) {
            pendingVideoMode = null;
            closeCameraSetup(true);
          } else if (
            rankingModal.classList.contains("show")
          ) {
            closeRankingModal();
          } else if ($("#hosuView").classList.contains("show")) {
            if (!$("#hosuMenu").classList.contains("hidden")) hardNavigate("home");
            else showHosuHome();
          } else if (
            workspace.classList.contains("show") ||
            results.classList.contains("show")
          ) {
            // チャレンジ中／結果画面 → チャレンジのモード選択。
            goMenu();
          } else if (
            !learningLessonView.classList.contains("hidden")
          ) {
            // 学習STEP詳細 → STEP一覧。
            showLearningStages(
              learningCurrentCategory
            );
          } else if (
            learningView.classList.contains("show") &&
            !learningStageView.classList.contains("hidden")
          ) {
            // STEP一覧 → 足し算・引き算などの種類選択。
            showLearningHome();
          } else if (
            learningView.classList.contains("show")
          ) {
            // 学習モードの種類選択 → アプリTOP。
            showHome();
          } else if (
            anzanView.classList.contains("show") &&
            (
              !anzanGameView.classList.contains("hidden") ||
              !anzanResultView.classList.contains("hidden")
            )
          ) {
            // 暗算プレイ中／結果 → 暗算レベル選択。
            showAnzanHome();
          } else if (
            anzanView.classList.contains("show")
          ) {
            // 暗算レベル選択 → アプリTOP。
            showHome();
          } else if (
            settingsView.classList.contains("show")
          ) {
            // 設定 → アプリTOP。
            showHome();
          } else if (
            !menuView.classList.contains("hidden")
          ) {
            // チャレンジのモード選択 → アプリTOP。
            showHome();
          } else {
            // アプリTOPでは外へ抜けず、そのまま維持。
            showHome();
          }
        } finally {
          // 次回のBackもアプリ内で処理できるようガードを戻す。
          setTimeout(() => {
            pushInAppBackGuard();
            handlingBrowserBack = false;
          }, 30);
        }
      }
    );
  }

  function goMenu() {
    learningInterrupt();
    const abandoningChallenge =
      workspace.classList.contains(
        "show"
      ) &&
      !results.classList.contains(
        "show"
      ) &&
      Boolean(currentMode);

    if (abandoningChallenge) {
      clearChallengeResumeState();
    }

    // Always restore the challenge menu before cleanup.
    forceChallengeMenuView();
    refreshChallengeMenuUi();

    if (
      sessionVideoActive ||
      cameraSetupModal.classList.contains("show")
    ) {
      runUiCleanup(discardChallengeVideoSession);
    }

    scoreAnimationToken += 1;
    runUiCleanup(closeRankingModal);
    runUiCleanup(stopTimer);
    runUiCleanup(stopBgm);
    runUiCleanup(hideSorobanHint);
    runUiCleanup(() => setVoiceAnswerEnabled(false));

    if ("speechSynthesis" in window) {
      runUiCleanup(() => cancelAppSpeech());
    }

    questionCard.classList.remove("hidden");
    currentMode = null;
    correctStreak = 0;
    runUiCleanup(() => updateStreakFrame(0));
  }

  const rankCelebrationCloseBtn =
    $("#rankCelebrationClose");

  if (rankCelebrationCloseBtn) {
    rankCelebrationCloseBtn.addEventListener(
      "click",
      closeRankCelebration
    );
  }

  if (rankCelebration) {
    rankCelebration.addEventListener(
      "click",
      (event) => {
        if (
          event.target ===
          rankCelebration
        ) {
          closeRankCelebration();
        }
      }
    );
  }

  if (medalResetBtn) {
    medalResetBtn.addEventListener(
      "click",
      handleMedalResetClick
    );
  }

  if (resumeChallengeBtn) {
    resumeChallengeBtn.addEventListener(
      "click",
      resumeSavedChallenge
    );
  }

  if (discardResumeBtn) {
    discardResumeBtn.addEventListener(
      "click",
      clearChallengeResumeState
    );
  }

  $("#learningStageBackBtn").addEventListener(
    "click",
    showLearningHome
  );

  $("#learningLessonBackBtn").addEventListener(
    "click",
    () => {
      showLearningStages(
        learningCurrentCategory
      );
    }
  );

  $("#learningReplayBtn").addEventListener(
    "click",
    () => {
      runLearningAnimation(
        true
      );
    }
  );

  learningPauseBtn.addEventListener(
    "click",
    () => {
      learningTick();
      if(learningClock){learningClock.paused=!learningAnimationPaused;cmEmit(learningActive,!learningAnimationPaused?"session_paused":"session_resumed",{reason:"explicit_pause",suspended_occurrence_id:learningActive?.questions[String(learningClock.index)]?.occurrence_id||null,last_response_id:null});}
      learningAnimationPaused =
        !learningAnimationPaused;

      learningPauseBtn.textContent =
        learningAnimationPaused
          ? "▶ 再開"
          : "Ⅱ 一時停止";

      if (
        learningAnimationPaused
      ) {
        stopLearningNarration();
      } else if (
        learningVoiceEnabled
      ) {
        const lesson =
          currentLearningLesson();

        if (lesson) {
          const displayedIndex =
            Math.max(
              0,
              Math.min(
                lesson.frames.length - 1,
                learningCurrentFrame - 1
              )
            );

          speakLearningFrame(
            lesson,
            displayedIndex
          );
        }
      }
    }
  );

  learningVoiceBtn.addEventListener(
    "click",
    () => {
      setLearningVoiceEnabled(
        !learningVoiceEnabled
      );
    }
  );

  $("#learningAgainBtn").addEventListener(
    "click",
    () => {
      const lesson =
        currentLearningLesson();

      if (lesson) {
        renderLearningQuiz(
          lesson
        );
      }

      runLearningAnimation(
        true
      );
    }
  );

  learningNextBtn.addEventListener(
    "click",
    goNextLearningLesson
  );

  root.querySelectorAll(".start-kuku").forEach((button) => {
    button.addEventListener("click", () => startKukuMode(button.dataset.kukuLevel));
  });

  $("#kukuKeypad").addEventListener("pointerup", (event) => {
    if (kukuLocked) return;
    const button = event.target.closest("button"); if (!button) return;
    const key = button.dataset.kukuKey; const action = button.dataset.kukuAction;
    if (key !== undefined) { if (kukuAnswerBuffer.length < 3) kukuAnswerBuffer = kukuAnswerBuffer === "0" ? key : kukuAnswerBuffer + key; updateKukuAnswerDisplay(); return; }
    if (action === "clear") kukuAnswerBuffer = ""; else if (action === "backspace") kukuAnswerBuffer = kukuAnswerBuffer.slice(0, -1);
    updateKukuAnswerDisplay();
  });

  $("#kukuSubmitBtn").addEventListener("click", submitKukuAnswer);
  kukuVoiceBtn.addEventListener("click", () => {
    kukuVoiceEnabled = !kukuVoiceEnabled; updateKukuButtons();
    if (kukuVoiceEnabled && !kukuLocked && !kukuPromptSpeaking) startKukuVoiceRecognition();
    else if (!kukuVoiceEnabled) { stopKukuRecognition(); kukuPrompt.textContent = "数字をタップして答えてね"; }
  });
  $("#kukuRetryBtn").addEventListener("click", () => startKukuMode(kukuLevel));
  $("#kukuMenuBtn").addEventListener("click", showKukuHome);

  root
    .querySelectorAll(
      ".start-anzan"
    )
    .forEach(
      (button) => {
        button.addEventListener(
          "click",
          () => {
            startAnzanMode(
              button.dataset.anzanLevel
            );
          }
        );
      }
    );

  $("#anzanKeypad").addEventListener(
    "pointerup",
    (event) => {
      if (anzanLocked) {
        return;
      }

      const button =
        event.target.closest(
          "button"
        );

      if (!button) {
        return;
      }

      const key =
        button.dataset.anzanKey;

      const action =
        button.dataset.anzanAction;

      if (
        key !== undefined
      ) {
        if (
          anzanAnswerBuffer.length < 8
        ) {
          anzanAnswerBuffer =
            anzanAnswerBuffer === "0"
              ? key
              : anzanAnswerBuffer + key;
        }

        updateAnzanAnswerDisplay();
        return;
      }

      if (
        action === "clear"
      ) {
        anzanAnswerBuffer = "";
      } else if (
        action === "backspace"
      ) {
        anzanAnswerBuffer =
          anzanAnswerBuffer.slice(
            0,
            -1
          );
      }

      updateAnzanAnswerDisplay();
    }
  );

  $("#anzanSubmitBtn").addEventListener(
    "click",
    submitAnzanAnswer
  );

  $("#anzanRetryBtn").addEventListener(
    "click",
    () => {
      startAnzanMode(
        anzanLevel
      );
    }
  );

  $("#anzanMenuBtn").addEventListener(
    "click",
    showAnzanHome
  );

  $("#settingTimeBtn").addEventListener(
    "click",
    () => {
      toggleTimeLimit();
      updateSettingsUi();
    }
  );

  $("#settingVoiceBtn").addEventListener(
    "click",
    () => {
      preferredVoiceAnswerEnabled =
        !preferredVoiceAnswerEnabled;

      saveBooleanSetting(
        VOICE_DEFAULT_SETTING_KEY,
        preferredVoiceAnswerEnabled
      );

      updateSettingsUi();
    }
  );

  $("#settingBgmBtn").addEventListener(
    "click",
    () => {
      bgmOn =
        !bgmOn;

      saveBooleanSetting(
        BGM_SETTING_KEY,
        bgmOn
      );

      updateBgmButton();
      updateSettingsUi();
    }
  );

  $("#settingLearningVoiceBtn").addEventListener(
    "click",
    () => {
      preferredLearningVoiceEnabled =
        !preferredLearningVoiceEnabled;

      learningVoiceEnabled =
        preferredLearningVoiceEnabled;

      saveBooleanSetting(
        LEARNING_VOICE_SETTING_KEY,
        preferredLearningVoiceEnabled
      );

      updateLearningVoiceUi();
      updateSettingsUi();
    }
  );

  $("#settingAnzanSpeedBtn").addEventListener(
    "click",
    cycleAnzanSpeed
  );

  voiceBtn.addEventListener("click", () => {
    preferredVoiceAnswerEnabled =
      !voiceAnswerEnabled;

    saveBooleanSetting(
      VOICE_DEFAULT_SETTING_KEY,
      preferredVoiceAnswerEnabled
    );

    setVoiceAnswerEnabled(
      preferredVoiceAnswerEnabled
    );

    updateSettingsUi();
  });

  hintBtn.addEventListener("click", () => {
    runSorobanHint();
  });

  hintPrevBtn.addEventListener("click", () => {
    moveManualHint(-1);
  });

  hintNextBtn.addEventListener("click", () => {
    moveManualHint(1);
  });

  hintMicAnswerBtn.addEventListener("click", () => {
    const step =
      hintManualSteps[
        hintManualIndex
      ];

    startHintQuestionRecognition(
      step
    );
  });

  hintNumberGrid.addEventListener("click", (event) => {
    const button =
      event.target.closest(
        "[data-hint-number]"
      );

    if (!button) {
      return;
    }

    const step =
      hintManualSteps[
        hintManualIndex
      ];

    submitHintComplementAnswer(
      step,
      Number(
        button.dataset.hintNumber
      ),
      "button"
    );
  });

  $("#hintCloseBtn").addEventListener("click", () => {
    learningPhase("answer");
    hideSorobanHint();
  });

  $("#keypad").addEventListener("pointerup", (event) => {
    const button = event.target.closest("button");
    if (!button || locked) return;

    const key = button.dataset.key;
    const action = button.dataset.action;

    if (key !== undefined) {
      const current = String(answerInput.value || "");

      if (current.length < 10) {
        answerInput.value =
          current === "0" ? key : current + key;
      }
      return;
    }

    if (action === "clear") {
      answerInput.value = "";
      return;
    }

    if (action === "backspace") {
      answerInput.value =
        String(answerInput.value || "").slice(0, -1);
    }
  });

  try {
    rebuildRankCertificationStateFromHistory();
    syncEarnedMedalsFromCurrentRank();
  } catch (error) {
    // 階級・メダルの復元失敗でアプリ全体を停止させない。
    rankCertificationState =
      emptyRankCertificationState(
        rankCertificationState?.resetAt || null,
        normalizeLegacyFloorByTrack(
          rankCertificationState?.legacyFloorByTrack
        )
      );
  }

  setupChallengeMedalSummaries();
  setupModeChallengeCountLabels();
  setupModeRankingButtons();

  root.querySelectorAll(
    ".challenge-operation-jump, .weakness-operation-jump"
  ).forEach((button) => {
    button.addEventListener(
      "click",
      () => {
        const target =
          root.querySelector(
            `#${button.dataset.target}`
          );

        if (target) {
          target.scrollIntoView({
            behavior: "smooth",
            block: "start"
          });
        }
      }
    );
  });

  root.querySelectorAll(".start-mode").forEach((button) => {
    button.addEventListener("click", () => {
      requestStartMode(
        button.dataset.mode,
        button
      );
    });
  });

  $("#rankingModalClose").addEventListener(
    "click",
    closeRankingModal
  );

  rankingModal.addEventListener(
    "click",
    (event) => {
      if (event.target === rankingModal) {
        closeRankingModal();
      }
    }
  );

  analysisVideoToggle.addEventListener(
    "click",
    toggleAnalysisVideo
  );

  cameraBeginBtn.addEventListener(
    "click",
    beginRecordedChallenge
  );

  $("#cameraNoVideoBtn").addEventListener(
    "click",
    beginChallengeWithoutVideo
  );

  $("#cameraCancelBtn").addEventListener(
    "click",
    () => {
      pendingVideoMode = null;
      closeCameraSetup(true);
    }
  );


  $("#downloadSessionVideoBtn").addEventListener(
    "click",
    downloadSessionVideo
  );

  $("#downloadSessionLogBtn").addEventListener(
    "click",
    downloadSessionLog
  );

  $("#answerForm").addEventListener("submit", (event) => {
    event.preventDefault();
    submitAnswer();
  });

  timeLimitBtn.addEventListener(
    "click",
    toggleTimeLimit
  );

  bgmBtn.addEventListener("click", toggleBgm);

  $("#restartChallengeBtn").addEventListener(
    "click",
    restartCurrentChallengeFromBeginning
  );

  $("#retryBtn").addEventListener("click", () => {
    if (!currentMode) {
      return;
    }

    if (activeWeaknessChallengeMode) {
      startWeaknessChallenge(
        currentMode
      );
      return;
    }

    requestStartMode(
      currentMode
    );
  });

  if (promoteBtn) {
    promoteBtn.addEventListener(
      "click",
      () => {
        if (promotedMode) {
          requestStartMode(
            promotedMode
          );
        }
      }
    );
  }

  window.addEventListener(
    "pagehide",
    () => {
      saveChallengeResumeState();
    }
  );

  document.addEventListener(
    "visibilitychange",
    () => {
      if (document.hidden) {
        saveChallengeResumeState();
      }
    }
  );

  timeLimitEnabled = true;
  timeDisplayEnabled =
    loadTimeDisplaySetting();

  bgmOn =
    loadBooleanSetting(
      BGM_SETTING_KEY,
      true
    );

  preferredVoiceAnswerEnabled =
    loadBooleanSetting(
      VOICE_DEFAULT_SETTING_KEY,
      false
    );

  preferredLearningVoiceEnabled =
    loadBooleanSetting(
      LEARNING_VOICE_SETTING_KEY,
      false
    );

  learningVoiceEnabled =
    preferredLearningVoiceEnabled;

  anzanSpeed =
    loadAnzanSpeed();

  analysisVideoEnabled = false;

  homeView.classList.remove("hidden");
  menuView.classList.add("hidden");
  learningView.classList.remove("show");
  anzanView.classList.remove("show");
  settingsView.classList.remove("show");
  weaknessView.classList.remove("show");
  workspace.classList.remove("show");

  updateTimeLimitUi();

  try {
    updateRankUi();
  } catch (error) {
    // メダル表示だけ失敗しても、ゲーム操作は継続する。
  }

  updateAnalysisVideoUi();
  updateLearningVoiceUi();
  updateBgmButton();
  updateSettingsUi();

  try {
    updateRankUi();
  } catch (error) {}

  renderLearningCategories();
  renderKukuMedalSummaries();
  refreshChallengeMenuUi();
  installInAppBackGuard();
  updateBgmButton();
  updateVoiceUi();
})();
</script>
</div>
"""

html = (
    HTML
    .replace("__BGM_URLS__", BGM_JSON)
    .replace("__APP_VERSION__", VERSION_JSON)
    .replace("__KUKU_GOLD_MEDAL__", KUKU_GOLD_MEDAL_URI)
    .replace("__KUKU_SILVER_MEDAL__", KUKU_SILVER_MEDAL_URI)
    .replace("__KUKU_BRONZE_MEDAL__", KUKU_BRONZE_MEDAL_URI)
)

@st.cache_resource(max_entries=2)
def stamp_component(frontend):
    digest=hashlib.sha256(frontend.encode('utf-8')).hexdigest()[:16]
    folder=Path(tempfile.gettempdir())/('soroban_stamp_component_'+digest)
    folder.mkdir(parents=True,exist_ok=True)
    (folder/'index.html').write_text(frontend,encoding='utf-8')
    return components.declare_component('soroban_stamp_'+digest,path=str(folder))


CHOKOMANA_MENUS = [{'source_app': 'soroban', 'menu_id': 'soroban:calculation:ba1', 'name': '初級・足し算1｜1桁・繰り上がりなし', 'category_key': 'calculation', 'skill_id': 'soroban:add', 'difficulty': 'ba1', 'difficulty_order': 1, 'question_count': 12, 'initial_estimate_seconds': 300, 'estimate_basis': '仮設定：1問あたり25秒×12問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': [], 'next_menu_ids': ['soroban:calculation:ba2'], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['チャレンジモード', '初級・足し算1｜1桁・繰り上がりなし'], 'mode_kind': 'challenge', 'progression_group_id': 'soroban:calculation:add'}, {'source_app': 'soroban', 'menu_id': 'soroban:calculation:ba2', 'name': '初級・足し算2｜1桁・繰り上がりあり', 'category_key': 'calculation', 'skill_id': 'soroban:add', 'difficulty': 'ba2', 'difficulty_order': 2, 'question_count': 12, 'initial_estimate_seconds': 300, 'estimate_basis': '仮設定：1問あたり25秒×12問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': ['soroban:add'], 'next_menu_ids': ['soroban:calculation:ba2x4'], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['チャレンジモード', '初級・足し算2｜1桁・繰り上がりあり'], 'mode_kind': 'challenge', 'progression_group_id': 'soroban:calculation:add'}, {'source_app': 'soroban', 'menu_id': 'soroban:calculation:ba2x4', 'name': '初級・足し算3｜1桁の数を4つ足す', 'category_key': 'calculation', 'skill_id': 'soroban:add', 'difficulty': 'ba2x4', 'difficulty_order': 3, 'question_count': 12, 'initial_estimate_seconds': 300, 'estimate_basis': '仮設定：1問あたり25秒×12問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': ['soroban:add'], 'next_menu_ids': ['soroban:calculation:ba3'], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['チャレンジモード', '初級・足し算3｜1桁の数を4つ足す'], 'mode_kind': 'challenge', 'progression_group_id': 'soroban:calculation:add'}, {'source_app': 'soroban', 'menu_id': 'soroban:calculation:ba3', 'name': '初級・足し算4｜2桁・繰り上がりなし', 'category_key': 'calculation', 'skill_id': 'soroban:add', 'difficulty': 'ba3', 'difficulty_order': 4, 'question_count': 12, 'initial_estimate_seconds': 300, 'estimate_basis': '仮設定：1問あたり25秒×12問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': ['soroban:add'], 'next_menu_ids': ['soroban:calculation:ba4'], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['チャレンジモード', '初級・足し算4｜2桁・繰り上がりなし'], 'mode_kind': 'challenge', 'progression_group_id': 'soroban:calculation:add'}, {'source_app': 'soroban', 'menu_id': 'soroban:calculation:ba4', 'name': '初級・足し算5｜2桁・繰り上がりあり', 'category_key': 'calculation', 'skill_id': 'soroban:add', 'difficulty': 'ba4', 'difficulty_order': 5, 'question_count': 12, 'initial_estimate_seconds': 300, 'estimate_basis': '仮設定：1問あたり25秒×12問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': ['soroban:add'], 'next_menu_ids': ['soroban:calculation:ba4x4'], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['チャレンジモード', '初級・足し算5｜2桁・繰り上がりあり'], 'mode_kind': 'challenge', 'progression_group_id': 'soroban:calculation:add'}, {'source_app': 'soroban', 'menu_id': 'soroban:calculation:ba4x4', 'name': '初級・足し算6｜2桁の数を4つ足す', 'category_key': 'calculation', 'skill_id': 'soroban:add', 'difficulty': 'ba4x4', 'difficulty_order': 6, 'question_count': 12, 'initial_estimate_seconds': 300, 'estimate_basis': '仮設定：1問あたり25秒×12問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': ['soroban:add'], 'next_menu_ids': ['soroban:calculation:ba5'], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['チャレンジモード', '初級・足し算6｜2桁の数を4つ足す'], 'mode_kind': 'challenge', 'progression_group_id': 'soroban:calculation:add'}, {'source_app': 'soroban', 'menu_id': 'soroban:calculation:ba5', 'name': '初級・足し算7｜3桁の足し算', 'category_key': 'calculation', 'skill_id': 'soroban:add', 'difficulty': 'ba5', 'difficulty_order': 7, 'question_count': 12, 'initial_estimate_seconds': 300, 'estimate_basis': '仮設定：1問あたり25秒×12問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': ['soroban:add'], 'next_menu_ids': ['soroban:calculation:ba5x4'], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['チャレンジモード', '初級・足し算7｜3桁の足し算'], 'mode_kind': 'challenge', 'progression_group_id': 'soroban:calculation:add'}, {'source_app': 'soroban', 'menu_id': 'soroban:calculation:ba5x4', 'name': '初級・足し算8｜3桁の数を4つ足す', 'category_key': 'calculation', 'skill_id': 'soroban:add', 'difficulty': 'ba5x4', 'difficulty_order': 8, 'question_count': 12, 'initial_estimate_seconds': 300, 'estimate_basis': '仮設定：1問あたり25秒×12問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': ['soroban:add'], 'next_menu_ids': [], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['チャレンジモード', '初級・足し算8｜3桁の数を4つ足す'], 'mode_kind': 'challenge', 'progression_group_id': 'soroban:calculation:add'}, {'source_app': 'soroban', 'menu_id': 'soroban:calculation:bs1', 'name': '初級・引き算1｜1桁・繰り下がりなし', 'category_key': 'calculation', 'skill_id': 'soroban:sub', 'difficulty': 'bs1', 'difficulty_order': 1, 'question_count': 12, 'initial_estimate_seconds': 300, 'estimate_basis': '仮設定：1問あたり25秒×12問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': [], 'next_menu_ids': ['soroban:calculation:bs2'], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['チャレンジモード', '初級・引き算1｜1桁・繰り下がりなし'], 'mode_kind': 'challenge', 'progression_group_id': 'soroban:calculation:sub'}, {'source_app': 'soroban', 'menu_id': 'soroban:calculation:bs2', 'name': '初級・引き算2｜1桁を引く・繰り下がりあり', 'category_key': 'calculation', 'skill_id': 'soroban:sub', 'difficulty': 'bs2', 'difficulty_order': 2, 'question_count': 12, 'initial_estimate_seconds': 300, 'estimate_basis': '仮設定：1問あたり25秒×12問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': ['soroban:sub'], 'next_menu_ids': ['soroban:calculation:bs2x4'], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['チャレンジモード', '初級・引き算2｜1桁を引く・繰り下がりあり'], 'mode_kind': 'challenge', 'progression_group_id': 'soroban:calculation:sub'}, {'source_app': 'soroban', 'menu_id': 'soroban:calculation:bs2x4', 'name': '初級・引き算3｜2桁から1桁の数を3回引く', 'category_key': 'calculation', 'skill_id': 'soroban:sub', 'difficulty': 'bs2x4', 'difficulty_order': 3, 'question_count': 12, 'initial_estimate_seconds': 300, 'estimate_basis': '仮設定：1問あたり25秒×12問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': ['soroban:sub'], 'next_menu_ids': ['soroban:calculation:bs3'], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['チャレンジモード', '初級・引き算3｜2桁から1桁の数を3回引く'], 'mode_kind': 'challenge', 'progression_group_id': 'soroban:calculation:sub'}, {'source_app': 'soroban', 'menu_id': 'soroban:calculation:bs3', 'name': '初級・引き算4｜2桁・繰り下がりなし', 'category_key': 'calculation', 'skill_id': 'soroban:sub', 'difficulty': 'bs3', 'difficulty_order': 4, 'question_count': 12, 'initial_estimate_seconds': 300, 'estimate_basis': '仮設定：1問あたり25秒×12問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': ['soroban:sub'], 'next_menu_ids': ['soroban:calculation:bs4'], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['チャレンジモード', '初級・引き算4｜2桁・繰り下がりなし'], 'mode_kind': 'challenge', 'progression_group_id': 'soroban:calculation:sub'}, {'source_app': 'soroban', 'menu_id': 'soroban:calculation:bs4', 'name': '初級・引き算5｜2桁・繰り下がりあり', 'category_key': 'calculation', 'skill_id': 'soroban:sub', 'difficulty': 'bs4', 'difficulty_order': 5, 'question_count': 12, 'initial_estimate_seconds': 300, 'estimate_basis': '仮設定：1問あたり25秒×12問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': ['soroban:sub'], 'next_menu_ids': ['soroban:calculation:bs4x4'], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['チャレンジモード', '初級・引き算5｜2桁・繰り下がりあり'], 'mode_kind': 'challenge', 'progression_group_id': 'soroban:calculation:sub'}, {'source_app': 'soroban', 'menu_id': 'soroban:calculation:bs4x4', 'name': '初級・引き算6｜2桁の数を4つ使う引き算', 'category_key': 'calculation', 'skill_id': 'soroban:sub', 'difficulty': 'bs4x4', 'difficulty_order': 6, 'question_count': 12, 'initial_estimate_seconds': 300, 'estimate_basis': '仮設定：1問あたり25秒×12問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': ['soroban:sub'], 'next_menu_ids': ['soroban:calculation:bs5'], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['チャレンジモード', '初級・引き算6｜2桁の数を4つ使う引き算'], 'mode_kind': 'challenge', 'progression_group_id': 'soroban:calculation:sub'}, {'source_app': 'soroban', 'menu_id': 'soroban:calculation:bs5', 'name': '初級・引き算7｜3桁の引き算', 'category_key': 'calculation', 'skill_id': 'soroban:sub', 'difficulty': 'bs5', 'difficulty_order': 7, 'question_count': 12, 'initial_estimate_seconds': 300, 'estimate_basis': '仮設定：1問あたり25秒×12問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': ['soroban:sub'], 'next_menu_ids': ['soroban:calculation:bs5x4'], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['チャレンジモード', '初級・引き算7｜3桁の引き算'], 'mode_kind': 'challenge', 'progression_group_id': 'soroban:calculation:sub'}, {'source_app': 'soroban', 'menu_id': 'soroban:calculation:bs5x4', 'name': '初級・引き算8｜3桁から2桁を4回引く', 'category_key': 'calculation', 'skill_id': 'soroban:sub', 'difficulty': 'bs5x4', 'difficulty_order': 8, 'question_count': 12, 'initial_estimate_seconds': 300, 'estimate_basis': '仮設定：1問あたり25秒×12問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': ['soroban:sub'], 'next_menu_ids': [], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['チャレンジモード', '初級・引き算8｜3桁から2桁を4回引く'], 'mode_kind': 'challenge', 'progression_group_id': 'soroban:calculation:sub'}, {'source_app': 'soroban', 'menu_id': 'soroban:calculation:mm1', 'name': '中級・掛け算1｜1桁×1桁', 'category_key': 'calculation', 'skill_id': 'soroban:mul', 'difficulty': 'mm1', 'difficulty_order': 1, 'question_count': 12, 'initial_estimate_seconds': 300, 'estimate_basis': '仮設定：1問あたり25秒×12問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': [], 'next_menu_ids': ['soroban:calculation:mm2'], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['チャレンジモード', '中級・掛け算1｜1桁×1桁'], 'mode_kind': 'challenge', 'progression_group_id': 'soroban:calculation:mul'}, {'source_app': 'soroban', 'menu_id': 'soroban:calculation:mm2', 'name': '中級・掛け算2｜2桁×1桁', 'category_key': 'calculation', 'skill_id': 'soroban:mul', 'difficulty': 'mm2', 'difficulty_order': 2, 'question_count': 12, 'initial_estimate_seconds': 300, 'estimate_basis': '仮設定：1問あたり25秒×12問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': ['soroban:mul'], 'next_menu_ids': ['soroban:calculation:mm3'], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['チャレンジモード', '中級・掛け算2｜2桁×1桁'], 'mode_kind': 'challenge', 'progression_group_id': 'soroban:calculation:mul'}, {'source_app': 'soroban', 'menu_id': 'soroban:calculation:mm3', 'name': '中級・掛け算3｜2桁×2桁', 'category_key': 'calculation', 'skill_id': 'soroban:mul', 'difficulty': 'mm3', 'difficulty_order': 3, 'question_count': 12, 'initial_estimate_seconds': 300, 'estimate_basis': '仮設定：1問あたり25秒×12問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': ['soroban:mul'], 'next_menu_ids': [], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['チャレンジモード', '中級・掛け算3｜2桁×2桁'], 'mode_kind': 'challenge', 'progression_group_id': 'soroban:calculation:mul'}, {'source_app': 'soroban', 'menu_id': 'soroban:calculation:md1', 'name': '中級・割り算1｜1〜81÷1桁', 'category_key': 'calculation', 'skill_id': 'soroban:div', 'difficulty': 'md1', 'difficulty_order': 1, 'question_count': 12, 'initial_estimate_seconds': 300, 'estimate_basis': '仮設定：1問あたり25秒×12問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': [], 'next_menu_ids': ['soroban:calculation:md2'], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['チャレンジモード', '中級・割り算1｜1〜81÷1桁'], 'mode_kind': 'challenge', 'progression_group_id': 'soroban:calculation:div'}, {'source_app': 'soroban', 'menu_id': 'soroban:calculation:md2', 'name': '中級・割り算2｜3桁÷1桁', 'category_key': 'calculation', 'skill_id': 'soroban:div', 'difficulty': 'md2', 'difficulty_order': 2, 'question_count': 12, 'initial_estimate_seconds': 300, 'estimate_basis': '仮設定：1問あたり25秒×12問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': ['soroban:div'], 'next_menu_ids': ['soroban:calculation:md3'], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['チャレンジモード', '中級・割り算2｜3桁÷1桁'], 'mode_kind': 'challenge', 'progression_group_id': 'soroban:calculation:div'}, {'source_app': 'soroban', 'menu_id': 'soroban:calculation:md3', 'name': '中級・割り算3｜3桁÷2桁', 'category_key': 'calculation', 'skill_id': 'soroban:div', 'difficulty': 'md3', 'difficulty_order': 3, 'question_count': 12, 'initial_estimate_seconds': 300, 'estimate_basis': '仮設定：1問あたり25秒×12問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': ['soroban:div'], 'next_menu_ids': [], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['チャレンジモード', '中級・割り算3｜3桁÷2桁'], 'mode_kind': 'challenge', 'progression_group_id': 'soroban:calculation:div'}, {'source_app': 'soroban', 'menu_id': 'soroban:calculation:a1', 'name': '上級1｜4桁の足し算・引き算', 'category_key': 'calculation', 'skill_id': 'soroban:advanced', 'difficulty': 'a1', 'difficulty_order': 1, 'question_count': 12, 'initial_estimate_seconds': 300, 'estimate_basis': '仮設定：1問あたり25秒×12問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': [], 'next_menu_ids': ['soroban:calculation:a2'], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['チャレンジモード', '上級1｜4桁の足し算・引き算'], 'mode_kind': 'challenge', 'progression_group_id': 'soroban:calculation:advanced'}, {'source_app': 'soroban', 'menu_id': 'soroban:calculation:a2', 'name': '上級2｜3桁×2桁 / 4桁÷2桁', 'category_key': 'calculation', 'skill_id': 'soroban:advanced', 'difficulty': 'a2', 'difficulty_order': 2, 'question_count': 12, 'initial_estimate_seconds': 300, 'estimate_basis': '仮設定：1問あたり25秒×12問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': ['soroban:advanced'], 'next_menu_ids': ['soroban:calculation:a3'], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['チャレンジモード', '上級2｜3桁×2桁 / 4桁÷2桁'], 'mode_kind': 'challenge', 'progression_group_id': 'soroban:calculation:advanced'}, {'source_app': 'soroban', 'menu_id': 'soroban:calculation:a3', 'name': '上級3｜3桁×3桁 / 5桁÷3桁', 'category_key': 'calculation', 'skill_id': 'soroban:advanced', 'difficulty': 'a3', 'difficulty_order': 3, 'question_count': 12, 'initial_estimate_seconds': 300, 'estimate_basis': '仮設定：1問あたり25秒×12問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': ['soroban:advanced'], 'next_menu_ids': [], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['チャレンジモード', '上級3｜3桁×3桁 / 5桁÷3桁'], 'mode_kind': 'challenge', 'progression_group_id': 'soroban:calculation:advanced'}, {'source_app': 'soroban', 'menu_id': 'soroban:hosu:add:1', 'name': '足し算・初級', 'category_key': 'hosu', 'skill_id': 'soroban:complement:add', 'difficulty': 'add:1', 'difficulty_order': 1, 'question_count': 12, 'initial_estimate_seconds': 480, 'estimate_basis': '仮設定：1問あたり40秒×12問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': ['soroban:add'], 'next_menu_ids': ['soroban:hosu:add:2'], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['補数名人', '足し算・初級'], 'mode_kind': 'challenge', 'progression_group_id': 'soroban:hosu:add'}, {'source_app': 'soroban', 'menu_id': 'soroban:hosu:add:2', 'name': '足し算・中級', 'category_key': 'hosu', 'skill_id': 'soroban:complement:add', 'difficulty': 'add:2', 'difficulty_order': 2, 'question_count': 12, 'initial_estimate_seconds': 600, 'estimate_basis': '仮設定：1問あたり50秒×12問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': ['soroban:add'], 'next_menu_ids': ['soroban:hosu:add:3'], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['補数名人', '足し算・中級'], 'mode_kind': 'challenge', 'progression_group_id': 'soroban:hosu:add'}, {'source_app': 'soroban', 'menu_id': 'soroban:hosu:add:3', 'name': '足し算・上級', 'category_key': 'hosu', 'skill_id': 'soroban:complement:add', 'difficulty': 'add:3', 'difficulty_order': 3, 'question_count': 12, 'initial_estimate_seconds': 720, 'estimate_basis': '仮設定：1問あたり60秒×12問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': ['soroban:add'], 'next_menu_ids': [], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['補数名人', '足し算・上級'], 'mode_kind': 'challenge', 'progression_group_id': 'soroban:hosu:add'}, {'source_app': 'soroban', 'menu_id': 'soroban:hosu:sub:1', 'name': '引き算・初級', 'category_key': 'hosu', 'skill_id': 'soroban:complement:sub', 'difficulty': 'sub:1', 'difficulty_order': 1, 'question_count': 12, 'initial_estimate_seconds': 480, 'estimate_basis': '仮設定：1問あたり40秒×12問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': ['soroban:sub'], 'next_menu_ids': ['soroban:hosu:sub:2'], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['補数名人', '引き算・初級'], 'mode_kind': 'challenge', 'progression_group_id': 'soroban:hosu:sub'}, {'source_app': 'soroban', 'menu_id': 'soroban:hosu:sub:2', 'name': '引き算・中級', 'category_key': 'hosu', 'skill_id': 'soroban:complement:sub', 'difficulty': 'sub:2', 'difficulty_order': 2, 'question_count': 12, 'initial_estimate_seconds': 600, 'estimate_basis': '仮設定：1問あたり50秒×12問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': ['soroban:sub'], 'next_menu_ids': ['soroban:hosu:sub:3'], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['補数名人', '引き算・中級'], 'mode_kind': 'challenge', 'progression_group_id': 'soroban:hosu:sub'}, {'source_app': 'soroban', 'menu_id': 'soroban:hosu:sub:3', 'name': '引き算・上級', 'category_key': 'hosu', 'skill_id': 'soroban:complement:sub', 'difficulty': 'sub:3', 'difficulty_order': 3, 'question_count': 12, 'initial_estimate_seconds': 720, 'estimate_basis': '仮設定：1問あたり60秒×12問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': ['soroban:sub'], 'next_menu_ids': [], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['補数名人', '引き算・上級'], 'mode_kind': 'challenge', 'progression_group_id': 'soroban:hosu:sub'}, {'source_app': 'soroban', 'menu_id': 'soroban:kuku:1', 'name': '初級', 'category_key': 'kuku', 'skill_id': 'soroban:multiplication', 'difficulty': '1', 'difficulty_order': 1, 'question_count': 10, 'initial_estimate_seconds': 50, 'estimate_basis': '仮設定：1問あたり5秒×10問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': [], 'next_menu_ids': ['soroban:kuku:2'], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['九九名人', '初級'], 'mode_kind': 'challenge', 'progression_group_id': 'soroban:kuku'}, {'source_app': 'soroban', 'menu_id': 'soroban:kuku:2', 'name': '中級', 'category_key': 'kuku', 'skill_id': 'soroban:multiplication', 'difficulty': '2', 'difficulty_order': 2, 'question_count': 10, 'initial_estimate_seconds': 50, 'estimate_basis': '仮設定：1問あたり5秒×10問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': ['soroban:multiplication'], 'next_menu_ids': ['soroban:kuku:3'], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['九九名人', '中級'], 'mode_kind': 'challenge', 'progression_group_id': 'soroban:kuku'}, {'source_app': 'soroban', 'menu_id': 'soroban:kuku:3', 'name': '上級・完全ランダム10問', 'category_key': 'kuku', 'skill_id': 'soroban:multiplication', 'difficulty': '3', 'difficulty_order': 3, 'question_count': 10, 'initial_estimate_seconds': 50, 'estimate_basis': '仮設定：1問あたり5秒×10問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': ['soroban:multiplication'], 'next_menu_ids': ['soroban:kuku:4'], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['九九名人', '上級・完全ランダム10問'], 'mode_kind': 'challenge', 'progression_group_id': 'soroban:kuku'}, {'source_app': 'soroban', 'menu_id': 'soroban:kuku:4', 'name': '特級・完全ランダム30問', 'category_key': 'kuku', 'skill_id': 'soroban:multiplication', 'difficulty': '4', 'difficulty_order': 4, 'question_count': 30, 'initial_estimate_seconds': 150, 'estimate_basis': '仮設定：1問あたり5秒×30問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': ['soroban:multiplication'], 'next_menu_ids': ['soroban:kuku:5'], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['九九名人', '特級・完全ランダム30問'], 'mode_kind': 'challenge', 'progression_group_id': 'soroban:kuku'}, {'source_app': 'soroban', 'menu_id': 'soroban:kuku:5', 'name': '名人', 'category_key': 'kuku', 'skill_id': 'soroban:multiplication', 'difficulty': '5', 'difficulty_order': 5, 'question_count': 90, 'initial_estimate_seconds': 450, 'estimate_basis': '仮設定：1問あたり5秒×90問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': ['soroban:multiplication'], 'next_menu_ids': [], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['九九名人', '名人'], 'mode_kind': 'challenge', 'progression_group_id': 'soroban:kuku'}, {'source_app': 'soroban', 'menu_id': 'soroban:anzan:1', 'name': '初級', 'category_key': 'anzan', 'skill_id': 'soroban:mental_arithmetic', 'difficulty': '1', 'difficulty_order': 1, 'question_count': 10, 'initial_estimate_seconds': 150, 'estimate_basis': '仮設定：1問あたり15秒×10問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': [], 'next_menu_ids': ['soroban:anzan:2'], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['暗算名人', '初級'], 'mode_kind': 'challenge', 'progression_group_id': 'soroban:anzan'}, {'source_app': 'soroban', 'menu_id': 'soroban:anzan:2', 'name': '中級', 'category_key': 'anzan', 'skill_id': 'soroban:mental_arithmetic', 'difficulty': '2', 'difficulty_order': 2, 'question_count': 10, 'initial_estimate_seconds': 200, 'estimate_basis': '仮設定：1問あたり20秒×10問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': [], 'next_menu_ids': ['soroban:anzan:3'], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['暗算名人', '中級'], 'mode_kind': 'challenge', 'progression_group_id': 'soroban:anzan'}, {'source_app': 'soroban', 'menu_id': 'soroban:anzan:3', 'name': '上級', 'category_key': 'anzan', 'skill_id': 'soroban:mental_arithmetic', 'difficulty': '3', 'difficulty_order': 3, 'question_count': 10, 'initial_estimate_seconds': 250, 'estimate_basis': '仮設定：1問あたり25秒×10問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': [], 'next_menu_ids': [], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['暗算名人', '上級'], 'mode_kind': 'challenge', 'progression_group_id': 'soroban:anzan'}, {'source_app': 'soroban', 'menu_id': 'soroban:tutorial:add1', 'name': '1〜4をそのまま足す', 'category_key': 'calculation', 'skill_id': 'soroban:lesson:add1', 'difficulty': 'add1', 'difficulty_order': 1, 'question_count': 1, 'initial_estimate_seconds': 90, 'estimate_basis': '仮設定：1問あたり90秒×1問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': [], 'next_menu_ids': ['soroban:tutorial:add2'], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['珠の動きで学ぶ', '足し算', '1〜4をそのまま足す'], 'mode_kind': 'tutorial', 'progression_group_id': 'soroban:tutorial:add'}, {'source_app': 'soroban', 'menu_id': 'soroban:tutorial:add2', 'name': '5珠と1珠を組み合わせる', 'category_key': 'calculation', 'skill_id': 'soroban:lesson:add2', 'difficulty': 'add2', 'difficulty_order': 2, 'question_count': 1, 'initial_estimate_seconds': 90, 'estimate_basis': '仮設定：1問あたり90秒×1問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': ['soroban:lesson:add1'], 'next_menu_ids': ['soroban:tutorial:add3'], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['珠の動きで学ぶ', '足し算', '5珠と1珠を組み合わせる'], 'mode_kind': 'tutorial', 'progression_group_id': 'soroban:tutorial:add'}, {'source_app': 'soroban', 'menu_id': 'soroban:tutorial:add3', 'name': '5の補数で足す', 'category_key': 'calculation', 'skill_id': 'soroban:lesson:add3', 'difficulty': 'add3', 'difficulty_order': 3, 'question_count': 1, 'initial_estimate_seconds': 90, 'estimate_basis': '仮設定：1問あたり90秒×1問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': ['soroban:lesson:add2'], 'next_menu_ids': ['soroban:tutorial:add4'], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['珠の動きで学ぶ', '足し算', '5の補数で足す'], 'mode_kind': 'tutorial', 'progression_group_id': 'soroban:tutorial:add'}, {'source_app': 'soroban', 'menu_id': 'soroban:tutorial:add4', 'name': '10の補数で繰り上がる', 'category_key': 'calculation', 'skill_id': 'soroban:lesson:add4', 'difficulty': 'add4', 'difficulty_order': 4, 'question_count': 1, 'initial_estimate_seconds': 90, 'estimate_basis': '仮設定：1問あたり90秒×1問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': ['soroban:lesson:add3'], 'next_menu_ids': ['soroban:tutorial:add5'], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['珠の動きで学ぶ', '足し算', '10の補数で繰り上がる'], 'mode_kind': 'tutorial', 'progression_group_id': 'soroban:tutorial:add'}, {'source_app': 'soroban', 'menu_id': 'soroban:tutorial:add5', 'name': '2桁の繰り上がり', 'category_key': 'calculation', 'skill_id': 'soroban:lesson:add5', 'difficulty': 'add5', 'difficulty_order': 5, 'question_count': 1, 'initial_estimate_seconds': 90, 'estimate_basis': '仮設定：1問あたり90秒×1問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': ['soroban:lesson:add4'], 'next_menu_ids': [], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['珠の動きで学ぶ', '足し算', '2桁の繰り上がり'], 'mode_kind': 'tutorial', 'progression_group_id': 'soroban:tutorial:add'}, {'source_app': 'soroban', 'menu_id': 'soroban:tutorial:sub1', 'name': 'そのまま引く', 'category_key': 'calculation', 'skill_id': 'soroban:lesson:sub1', 'difficulty': 'sub1', 'difficulty_order': 1, 'question_count': 1, 'initial_estimate_seconds': 90, 'estimate_basis': '仮設定：1問あたり90秒×1問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': [], 'next_menu_ids': ['soroban:tutorial:sub2'], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['珠の動きで学ぶ', '引き算', 'そのまま引く'], 'mode_kind': 'tutorial', 'progression_group_id': 'soroban:tutorial:sub'}, {'source_app': 'soroban', 'menu_id': 'soroban:tutorial:sub2', 'name': '5珠から直接引く', 'category_key': 'calculation', 'skill_id': 'soroban:lesson:sub2', 'difficulty': 'sub2', 'difficulty_order': 2, 'question_count': 1, 'initial_estimate_seconds': 90, 'estimate_basis': '仮設定：1問あたり90秒×1問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': ['soroban:lesson:sub1'], 'next_menu_ids': ['soroban:tutorial:sub3'], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['珠の動きで学ぶ', '引き算', '5珠から直接引く'], 'mode_kind': 'tutorial', 'progression_group_id': 'soroban:tutorial:sub'}, {'source_app': 'soroban', 'menu_id': 'soroban:tutorial:sub3', 'name': '5の補数で引く', 'category_key': 'calculation', 'skill_id': 'soroban:lesson:sub3', 'difficulty': 'sub3', 'difficulty_order': 3, 'question_count': 1, 'initial_estimate_seconds': 90, 'estimate_basis': '仮設定：1問あたり90秒×1問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': ['soroban:lesson:sub2'], 'next_menu_ids': ['soroban:tutorial:sub4'], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['珠の動きで学ぶ', '引き算', '5の補数で引く'], 'mode_kind': 'tutorial', 'progression_group_id': 'soroban:tutorial:sub'}, {'source_app': 'soroban', 'menu_id': 'soroban:tutorial:sub4', 'name': '10の補数で繰り下がる', 'category_key': 'calculation', 'skill_id': 'soroban:lesson:sub4', 'difficulty': 'sub4', 'difficulty_order': 4, 'question_count': 1, 'initial_estimate_seconds': 90, 'estimate_basis': '仮設定：1問あたり90秒×1問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': ['soroban:lesson:sub3'], 'next_menu_ids': ['soroban:tutorial:sub5'], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['珠の動きで学ぶ', '引き算', '10の補数で繰り下がる'], 'mode_kind': 'tutorial', 'progression_group_id': 'soroban:tutorial:sub'}, {'source_app': 'soroban', 'menu_id': 'soroban:tutorial:sub5', 'name': '2桁の繰り下がり', 'category_key': 'calculation', 'skill_id': 'soroban:lesson:sub5', 'difficulty': 'sub5', 'difficulty_order': 5, 'question_count': 1, 'initial_estimate_seconds': 90, 'estimate_basis': '仮設定：1問あたり90秒×1問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': ['soroban:lesson:sub4'], 'next_menu_ids': [], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['珠の動きで学ぶ', '引き算', '2桁の繰り下がり'], 'mode_kind': 'tutorial', 'progression_group_id': 'soroban:tutorial:sub'}, {'source_app': 'soroban', 'menu_id': 'soroban:tutorial:mul1', 'name': '九九の答えを珠に置く', 'category_key': 'calculation', 'skill_id': 'soroban:lesson:mul1', 'difficulty': 'mul1', 'difficulty_order': 1, 'question_count': 1, 'initial_estimate_seconds': 90, 'estimate_basis': '仮設定：1問あたり90秒×1問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': [], 'next_menu_ids': ['soroban:tutorial:mul2'], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['珠の動きで学ぶ', '掛け算', '九九の答えを珠に置く'], 'mode_kind': 'tutorial', 'progression_group_id': 'soroban:tutorial:mul'}, {'source_app': 'soroban', 'menu_id': 'soroban:tutorial:mul2', 'name': '2桁×1桁の部分積', 'category_key': 'calculation', 'skill_id': 'soroban:lesson:mul2', 'difficulty': 'mul2', 'difficulty_order': 2, 'question_count': 1, 'initial_estimate_seconds': 90, 'estimate_basis': '仮設定：1問あたり90秒×1問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': ['soroban:lesson:mul1'], 'next_menu_ids': ['soroban:tutorial:mul3'], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['珠の動きで学ぶ', '掛け算', '2桁×1桁の部分積'], 'mode_kind': 'tutorial', 'progression_group_id': 'soroban:tutorial:mul'}, {'source_app': 'soroban', 'menu_id': 'soroban:tutorial:mul3', 'name': '2桁×2桁', 'category_key': 'calculation', 'skill_id': 'soroban:lesson:mul3', 'difficulty': 'mul3', 'difficulty_order': 3, 'question_count': 1, 'initial_estimate_seconds': 90, 'estimate_basis': '仮設定：1問あたり90秒×1問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': ['soroban:lesson:mul2'], 'next_menu_ids': ['soroban:tutorial:mul4'], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['珠の動きで学ぶ', '掛け算', '2桁×2桁'], 'mode_kind': 'tutorial', 'progression_group_id': 'soroban:tutorial:mul'}, {'source_app': 'soroban', 'menu_id': 'soroban:tutorial:mul4', 'name': '0がある数の位取り', 'category_key': 'calculation', 'skill_id': 'soroban:lesson:mul4', 'difficulty': 'mul4', 'difficulty_order': 4, 'question_count': 1, 'initial_estimate_seconds': 90, 'estimate_basis': '仮設定：1問あたり90秒×1問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': ['soroban:lesson:mul3'], 'next_menu_ids': [], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['珠の動きで学ぶ', '掛け算', '0がある数の位取り'], 'mode_kind': 'tutorial', 'progression_group_id': 'soroban:tutorial:mul'}, {'source_app': 'soroban', 'menu_id': 'soroban:tutorial:div1', 'name': '1桁÷1桁', 'category_key': 'calculation', 'skill_id': 'soroban:lesson:div1', 'difficulty': 'div1', 'difficulty_order': 1, 'question_count': 1, 'initial_estimate_seconds': 90, 'estimate_basis': '仮設定：1問あたり90秒×1問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': [], 'next_menu_ids': ['soroban:tutorial:div2'], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['珠の動きで学ぶ', '割り算', '1桁÷1桁'], 'mode_kind': 'tutorial', 'progression_group_id': 'soroban:tutorial:div'}, {'source_app': 'soroban', 'menu_id': 'soroban:tutorial:div2', 'name': '2桁÷1桁', 'category_key': 'calculation', 'skill_id': 'soroban:lesson:div2', 'difficulty': 'div2', 'difficulty_order': 2, 'question_count': 1, 'initial_estimate_seconds': 90, 'estimate_basis': '仮設定：1問あたり90秒×1問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': ['soroban:lesson:div1'], 'next_menu_ids': ['soroban:tutorial:div3'], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['珠の動きで学ぶ', '割り算', '2桁÷1桁'], 'mode_kind': 'tutorial', 'progression_group_id': 'soroban:tutorial:div'}, {'source_app': 'soroban', 'menu_id': 'soroban:tutorial:div3', 'name': '3桁÷1桁', 'category_key': 'calculation', 'skill_id': 'soroban:lesson:div3', 'difficulty': 'div3', 'difficulty_order': 3, 'question_count': 1, 'initial_estimate_seconds': 90, 'estimate_basis': '仮設定：1問あたり90秒×1問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': ['soroban:lesson:div2'], 'next_menu_ids': ['soroban:tutorial:div4'], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['珠の動きで学ぶ', '割り算', '3桁÷1桁'], 'mode_kind': 'tutorial', 'progression_group_id': 'soroban:tutorial:div'}, {'source_app': 'soroban', 'menu_id': 'soroban:tutorial:div4', 'name': '2桁で割る', 'category_key': 'calculation', 'skill_id': 'soroban:lesson:div4', 'difficulty': 'div4', 'difficulty_order': 4, 'question_count': 1, 'initial_estimate_seconds': 90, 'estimate_basis': '仮設定：1問あたり90秒×1問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': ['soroban:lesson:div3'], 'next_menu_ids': [], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['珠の動きで学ぶ', '割り算', '2桁で割る'], 'mode_kind': 'tutorial', 'progression_group_id': 'soroban:tutorial:div'}, {'source_app': 'soroban', 'menu_id': 'soroban:kuku:read:1', 'name': '1の段・読み上げ', 'category_key': 'kuku', 'skill_id': 'soroban:kuku:1', 'difficulty': 'read', 'difficulty_order': 1, 'question_count': 1, 'initial_estimate_seconds': 30, 'estimate_basis': '仮設定：1問あたり30秒×1問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': [], 'next_menu_ids': [], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['九九名人', '九九一覧表', '1の段の読み上げ'], 'mode_kind': 'reading', 'progression_group_id': 'soroban:kuku:reading'}, {'source_app': 'soroban', 'menu_id': 'soroban:kuku:read:2', 'name': '2の段・読み上げ', 'category_key': 'kuku', 'skill_id': 'soroban:kuku:2', 'difficulty': 'read', 'difficulty_order': 2, 'question_count': 1, 'initial_estimate_seconds': 30, 'estimate_basis': '仮設定：1問あたり30秒×1問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': [], 'next_menu_ids': [], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['九九名人', '九九一覧表', '2の段の読み上げ'], 'mode_kind': 'reading', 'progression_group_id': 'soroban:kuku:reading'}, {'source_app': 'soroban', 'menu_id': 'soroban:kuku:read:3', 'name': '3の段・読み上げ', 'category_key': 'kuku', 'skill_id': 'soroban:kuku:3', 'difficulty': 'read', 'difficulty_order': 3, 'question_count': 1, 'initial_estimate_seconds': 30, 'estimate_basis': '仮設定：1問あたり30秒×1問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': [], 'next_menu_ids': [], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['九九名人', '九九一覧表', '3の段の読み上げ'], 'mode_kind': 'reading', 'progression_group_id': 'soroban:kuku:reading'}, {'source_app': 'soroban', 'menu_id': 'soroban:kuku:read:4', 'name': '4の段・読み上げ', 'category_key': 'kuku', 'skill_id': 'soroban:kuku:4', 'difficulty': 'read', 'difficulty_order': 4, 'question_count': 1, 'initial_estimate_seconds': 30, 'estimate_basis': '仮設定：1問あたり30秒×1問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': [], 'next_menu_ids': [], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['九九名人', '九九一覧表', '4の段の読み上げ'], 'mode_kind': 'reading', 'progression_group_id': 'soroban:kuku:reading'}, {'source_app': 'soroban', 'menu_id': 'soroban:kuku:read:5', 'name': '5の段・読み上げ', 'category_key': 'kuku', 'skill_id': 'soroban:kuku:5', 'difficulty': 'read', 'difficulty_order': 5, 'question_count': 1, 'initial_estimate_seconds': 30, 'estimate_basis': '仮設定：1問あたり30秒×1問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': [], 'next_menu_ids': [], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['九九名人', '九九一覧表', '5の段の読み上げ'], 'mode_kind': 'reading', 'progression_group_id': 'soroban:kuku:reading'}, {'source_app': 'soroban', 'menu_id': 'soroban:kuku:read:6', 'name': '6の段・読み上げ', 'category_key': 'kuku', 'skill_id': 'soroban:kuku:6', 'difficulty': 'read', 'difficulty_order': 6, 'question_count': 1, 'initial_estimate_seconds': 30, 'estimate_basis': '仮設定：1問あたり30秒×1問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': [], 'next_menu_ids': [], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['九九名人', '九九一覧表', '6の段の読み上げ'], 'mode_kind': 'reading', 'progression_group_id': 'soroban:kuku:reading'}, {'source_app': 'soroban', 'menu_id': 'soroban:kuku:read:7', 'name': '7の段・読み上げ', 'category_key': 'kuku', 'skill_id': 'soroban:kuku:7', 'difficulty': 'read', 'difficulty_order': 7, 'question_count': 1, 'initial_estimate_seconds': 30, 'estimate_basis': '仮設定：1問あたり30秒×1問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': [], 'next_menu_ids': [], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['九九名人', '九九一覧表', '7の段の読み上げ'], 'mode_kind': 'reading', 'progression_group_id': 'soroban:kuku:reading'}, {'source_app': 'soroban', 'menu_id': 'soroban:kuku:read:8', 'name': '8の段・読み上げ', 'category_key': 'kuku', 'skill_id': 'soroban:kuku:8', 'difficulty': 'read', 'difficulty_order': 8, 'question_count': 1, 'initial_estimate_seconds': 30, 'estimate_basis': '仮設定：1問あたり30秒×1問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': [], 'next_menu_ids': [], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['九九名人', '九九一覧表', '8の段の読み上げ'], 'mode_kind': 'reading', 'progression_group_id': 'soroban:kuku:reading'}, {'source_app': 'soroban', 'menu_id': 'soroban:kuku:read:9', 'name': '9の段・読み上げ', 'category_key': 'kuku', 'skill_id': 'soroban:kuku:9', 'difficulty': 'read', 'difficulty_order': 9, 'question_count': 1, 'initial_estimate_seconds': 30, 'estimate_basis': '仮設定：1問あたり30秒×1問。実測による裏付けは未取得。', 'estimate_kind': 'provisional', 'prerequisite_skill_ids': [], 'next_menu_ids': [], 'target_age_min': None, 'target_age_max': None, 'selection_steps': ['九九名人', '九九一覧表', '9の段の読み上げ'], 'mode_kind': 'reading', 'progression_group_id': 'soroban:kuku:reading'}]

# Chokomana integration. Service credentials are used exclusively on the server.
# --chokomana-sql / --chokomana-spec exports setup material without starting Streamlit.
def cm_config():
    from urllib.parse import urlparse
    try:
        url=str(st.secrets.get('SUPABASE_URL','')).rstrip('/')
        key=str(st.secrets.get('SUPABASE_SERVICE_ROLE_KEY',''))
    except Exception:
        return None
    if urlparse(url).hostname!='keewulninyoeylgflshb.supabase.co' or not key:
        return None
    return url,key


def cm_request(method,path,payload=None,params=None,prefer=None):
    from urllib.request import Request,urlopen
    from urllib.parse import urlencode
    config=cm_config()
    if not config: raise StampSaveError('missing_secrets')
    url,key=config
    headers={'apikey':key,'Content-Type':'application/json'}
    if not key.startswith('sb_secret_'):headers['Authorization']='Bearer '+key
    if prefer:headers['Prefer']=prefer
    target=url+path+('?' + urlencode(params) if params else '')
    data=json.dumps(payload).encode() if payload is not None else None
    with urlopen(Request(target,data=data,headers=headers,method=method),timeout=6) as response:
        raw=response.read()
        return json.loads(raw) if raw else None


class StampSaveError(ValueError):
    def __init__(self,code):super().__init__(code);self.code=code


def cm_device_hash(token):
    import re
    if not isinstance(token,str) or not re.fullmatch('[a-f0-9]{64}',token):
        raise StampSaveError('invalid_device')
    return hashlib.sha256(('soroban:'+token).encode()).hexdigest()


def cm_resolve_identity(token,consume=False):
    from datetime import datetime,timezone
    from uuid import UUID
    device_hash=cm_device_hash(token)
    if not cm_config():return ''
    ticket=st.query_params.get('cm_launch') if consume else None
    if ticket:
        import re
        if not isinstance(ticket,str) or not re.fullmatch('[A-Za-z0-9_-]{32,256}',ticket):
            raise StampSaveError('invalid_ticket')
        rows=cm_request('PATCH','/rest/v1/chokomana_launch_tickets',
            {'used_at':datetime.now(timezone.utc).isoformat()},
            {'ticket_hash':'eq.'+hashlib.sha256(ticket.encode()).hexdigest(),
             'source_app':'eq.soroban','used_at':'is.null',
             'expires_at':'gt.'+datetime.now(timezone.utc).isoformat(),'select':'profile_id'},
             'return=representation')
        # A replay never grants a new browser the ticket's identity.
        if rows and len(rows)==1:
            profile=str(UUID(rows[0]['profile_id']))
            cm_request('POST','/rest/v1/chokomana_device_links',
                {'device_hash':device_hash,'source_app':'soroban','profile_id':profile},
                {'on_conflict':'device_hash'},'resolution=merge-duplicates,return=minimal')
        try:del st.query_params['cm_launch']
        except Exception:pass
    rows=cm_request('GET','/rest/v1/chokomana_device_links',params={
        'device_hash':'eq.'+device_hash,'source_app':'eq.soroban','select':'profile_id','limit':'1'})
    return str(UUID(rows[0]['profile_id'])) if rows else ''


def stamp_profile_id():
    return st.session_state.get('cm_verified_profile','')


def cm_validate_record(record,profile):
    from uuid import UUID
    from datetime import datetime,timezone
    import math
    if not isinstance(record,dict) or record.get('schema_version')!=3 or record.get('profile_id')!=profile:
        raise StampSaveError('profile_mismatch')
    if not profile:raise StampSaveError('missing_profile')
    category=record.get('category_key')
    if category not in ('calculation','hosu','kuku','anzan'):raise StampSaveError('invalid_record')
    def date(value):
        d=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        if d.tzinfo is None:raise ValueError()
        return d.astimezone(timezone.utc).isoformat()
    try:
        attempt=str(UUID(record['attempt_id']));start=date(record['started_at']);end=date(record['finished_at'])
    except Exception:raise StampSaveError('invalid_record') from None
    total,correct=record.get('total_count'),record.get('correct_count')
    if type(total)!=int or type(correct)!=int or not 1<=total<=100 or not 0<=correct<=total:raise StampSaveError('invalid_score')
    status=record.get('status')
    if status not in ('completed','interrupted'):raise StampSaveError('invalid_status')
    answers=record.get('answers',{})
    if not isinstance(answers,dict) or len(answers)>total or any(type(v)!=bool for v in answers.values()) or sum(answers.values())!=correct:raise StampSaveError('invalid_score')
    menu=next((m for m in CHOKOMANA_MENUS if m['menu_id']==record.get('menu_id')),None)
    if not menu or menu['category_key']!=category:raise StampSaveError('invalid_menu')
    if status=='completed' and len(answers)!=total and menu['mode_kind']!='reading':raise StampSaveError('incomplete_attempt')
    if status=='completed' and menu['mode_kind']=='challenge' and record.get('grade') not in ('gold','silver','bronze','white'):raise StampSaveError('invalid_grade')
    time_keys=('answer_seconds','explanation_seconds','review_seconds','hidden_seconds','break_seconds','network_wait_seconds','unmeasured_seconds')
    def duration(v):
        if type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=31536000:raise StampSaveError('invalid_time')
        return round(float(v),3)
    def times(obj):
        if not isinstance(obj,dict):raise StampSaveError('invalid_time')
        return {key:duration(obj.get(key,0)) for key in time_keys}
    timing=times(record.get('time'))
    active=sum(timing[k] for k in time_keys[:3])
    elapsed=(datetime.fromisoformat(end)-datetime.fromisoformat(start)).total_seconds()
    # Stamp eligibility does not depend on browser wall-clock accuracy; event timing is separately quality flagged.
    elapsed=max(0,elapsed)
    questions=record.get('questions')
    if not isinstance(questions,dict) or len(questions)>total:raise StampSaveError('invalid_questions')
    clean_questions=[]
    for key,q in questions.items():
        if not key.isdigit() or not 0<=int(key)<total or not isinstance(q,dict):raise StampSaveError('invalid_questions')
        pid=q.get('problem_id');skills=q.get('skill_ids')
        if not isinstance(pid,str) or not 0<len(pid)<=2000 or not isinstance(skills,list) or not 1<=len(skills)<=30 or any(not isinstance(s,str) or len(s)>160 for s in skills):raise StampSaveError('invalid_questions')
        first=q.get('first_correct')
        if first is not None and type(first)!=bool:raise StampSaveError('invalid_questions')
        retries=q.get('retry_count',0)
        if type(retries)!=int or not 0<=retries<=100000:raise StampSaveError('invalid_questions')
        clean_questions.append({'question_order':int(key)+1,'problem_id':pid,'skill_ids':skills,
            'difficulty':str(q.get('difficulty',''))[:160],'format':str(q.get('format','numeric'))[:60],
            'first_correct':first,'retry_count':retries,'hint_used':q.get('hint_used') is True,
            'explanation_used':q.get('explanation_used') is True,'same_problem_seen':q.get('same_problem_seen') is True,
            'variant_group':str(q.get('variant_group',''))[:200],'completed':q.get('completed') is True,
            'time':times(q.get('time'))})
    revision=record.get('revision')
    if type(revision)!=int or not 1<=revision<2147483647:raise StampSaveError('invalid_revision')
    return {'profile_id':profile,'source_app':'soroban','attempt_id':attempt,'category_key':category,
        'menu_id':menu['menu_id'],'skill_id':menu['skill_id'],'difficulty':str(record.get('difficulty',''))[:160],
        'difficulty_order':menu['difficulty_order'],'content_version':'soroban-material-167',
        'started_at':start,'finished_at':end,'status':status,'total_count':total,'correct_count':correct,
        'active_seconds':round(active,3),'elapsed_seconds':elapsed,'time':timing,'revision':revision,
        'timing_quality':str(record.get('timing_quality','unknown'))[:40],
        'storage_persistent':record.get('storage_persistent') is True,'questions':clean_questions,
        'daily_active_seconds':{str(k):duration(v) for k,v in record.get('daily_active_seconds',{}).items() if __import__('re').fullmatch(r'\d{4}-\d{2}-\d{2}',str(k))},
        'assignment_context':record.get('assignment_context') if isinstance(record.get('assignment_context'),dict) else {}}


def cm_stamp_row(record,grade):
    labels={'calculation':('そろばん・計算','算','さん'),'hosu':('補数名人','補','ほ'),
        'kuku':('九九名人','九','きゅう'),'anzan':('暗算名人','暗','あん')}
    label,char,reading=labels[record['category_key']]
    if grade not in ('gold','silver','bronze','white'):raise StampSaveError('invalid_grade')
    return {k:record[k] for k in ('profile_id','source_app','attempt_id','category_key','difficulty','correct_count','total_count','finished_at')}|{
        'category_label':label,'stamp_char':char,'reading':reading,'grade':grade}


CM_EVENT_TYPES={'session_started','item_presented','response_submitted','support_used','learning_activity',
 'time_interval_closed','session_paused','session_resumed','session_ended','legacy_import','record_corrected'}


def cm_validate_events(events,profile):
    from uuid import UUID
    from datetime import datetime
    if not profile or not isinstance(events,list) or len(events)>100:raise StampSaveError('invalid_batch')
    clean=[]
    for event in events:
        if not isinstance(event,dict) or event.get('schema_version')!=1 or event.get('profile_id')!=profile or event.get('source_app')!='soroban':raise StampSaveError('profile_mismatch')
        if len(json.dumps(event,ensure_ascii=False).encode())>65536:raise StampSaveError('event_too_large')
        e=dict(event)
        for key in ('event_id','attempt_id','segment_id'):
            try:e[key]=str(UUID(e[key]))
            except Exception:raise StampSaveError('invalid_id') from None
        if e.get('occurrence_id') is not None:
            try:e['occurrence_id']=str(UUID(e['occurrence_id']))
            except Exception:raise StampSaveError('invalid_id') from None
        if type(e.get('sequence'))!=int or not 1<=e['sequence']<2147483647 or e.get('event_type') not in CM_EVENT_TYPES:raise StampSaveError('invalid_event')
        if not isinstance(e.get('occurred_at'),str) or not e['occurred_at'].endswith('Z'):raise StampSaveError('invalid_date')
        try:datetime.fromisoformat(e['occurred_at'].replace('Z','+00:00'))
        except Exception:raise StampSaveError('invalid_date') from None
        for key in ('app_version','content_version'):
            if not isinstance(e.get(key),str) or not 0<len(e[key])<=100:raise StampSaveError('invalid_version')
        if e.get('question_id') is not None and (not isinstance(e['question_id'],str) or len(e['question_id'])>2000):raise StampSaveError('invalid_question')
        p=e.get('payload')
        if not isinstance(p,dict):raise StampSaveError('invalid_payload')
        if e['event_type']=='time_interval_closed':
            if p.get('phase') not in ('prompt','thinking','answering','feedback','explanation','exploration','reading_aloud','other'):raise StampSaveError('invalid_phase')
            for key in ('elapsed_ms','active_ms'):
                v=p.get(key)
                if key=='active_ms' and v is None:continue
                if type(v)!=int or not 0<=v<=31536000000:raise StampSaveError('invalid_time')
            if p.get('active_ms') is not None and p['active_ms']>p['elapsed_ms']:raise StampSaveError('invalid_time')
            ex=p.get('excluded_ms',{})
            if any(type(ex.get(k))!=int or ex[k]<0 for k in ('hidden','explicit_pause','blocking_wait')):raise StampSaveError('invalid_time')
            for key in ('start_at','end_at'):
                if not isinstance(p.get(key),str) or not p[key].endswith('Z'):raise StampSaveError('invalid_time')
                try:datetime.fromisoformat(p[key].replace('Z','+00:00'))
                except Exception:raise StampSaveError('invalid_time') from None
        if e['event_type']=='response_submitted':
            if p.get('response_status') not in ('answered','dont_know','skipped','timed_out'):raise StampSaveError('invalid_response')
            if p.get('assessment_method') not in ('automatic','self','parent','ai','unscored','legacy_unknown'):raise StampSaveError('invalid_assessment')
            if p.get('input_method') not in ('keyboard','keypad','choice','speech','self_check','other'):raise StampSaveError('invalid_input')
            if p.get('is_correct') is not None and type(p['is_correct'])!=bool:raise StampSaveError('invalid_correctness')
            if p.get('response_status')!='answered' and p.get('is_correct') is not None:raise StampSaveError('invalid_correctness')
            if p.get('timing_quality') not in ('complete','partial','estimated','unknown'):raise StampSaveError('invalid_quality')
            if p.get('speech_status') not in ('not_used','recognized','recognition_failed','uncertain','corrected'):raise StampSaveError('invalid_speech_status')
            try:UUID(p.get('response_id',''))
            except Exception:raise StampSaveError('invalid_response') from None
            if type(p.get('response_index'))!=int or p['response_index']<1:raise StampSaveError('invalid_response')
            latency=p.get('answer_latency_ms')
            if latency is not None and (type(latency)!=int or latency<0):raise StampSaveError('invalid_time')
        if e['event_type']=='support_used' and p.get('support_type') not in ('hint','explanation','answer','worked_example','parent','replay'):raise StampSaveError('invalid_support')
        if e['event_type']=='time_interval_closed' and p.get('timing_quality') not in ('complete','partial','estimated','unknown'):raise StampSaveError('invalid_quality')
        if e['event_type']=='item_presented' and p.get('presentation_kind') not in ('new','scheduled_repeat','retry'):raise StampSaveError('invalid_presentation')
        if e['event_type']=='session_started' and not any(m['menu_id']==p.get('menu_id') for m in CHOKOMANA_MENUS):raise StampSaveError('invalid_menu')
        if e['event_type']=='session_ended' and p.get('status') not in ('completed','abandoned','interrupted','timed_out'):raise StampSaveError('invalid_status')
        clean.append({k:e.get(k) for k in ('schema_version','event_id','profile_id','source_app','app_version','content_version','attempt_id','occurrence_id','question_id','segment_id','sequence','occurred_at','event_type','payload')})
    return clean


def cm_catalog_rows():
    rows=[];skills={}
    for m in CHOKOMANA_MENUS:
        group=m['progression_group_id']
        payload={'menu_id':m['menu_id'],'label':m['name'],'category_id':m['category_key'],
         'category_label':{'calculation':'そろばん・計算','hosu':'補数名人','kuku':'九九名人','anzan':'暗算名人'}[m['category_key']],
         'difficulty_id':m['difficulty'],'difficulty_label':m['difficulty'],'difficulty_order':m['difficulty_order'],
         'progression_group_id':group,'skill_ids':[m['skill_id']],'prerequisite_skill_ids':None,
         'mode_options':['learn'] if m['mode_kind']=='tutorial' else ['reading_aloud'] if m['mode_kind']=='reading' else ['challenge'],
         'question_count_default':m['question_count'],'question_count_options':[4,12] if m['category_key']=='calculation' and m['mode_kind']=='challenge' else [m['question_count']],
         'estimated_duration_ms':int(m['initial_estimate_seconds']*1000),'duration_basis':'provisional','duration_sample_count':0,
         'duration_estimate_note':m['estimate_basis'],'age_min':None,'age_max':None,'age_basis':None,
         'launch_url':'','supports_direct_launch':False,'selection_instructions':m['selection_steps'],'is_active':True,
         'available_skill_ids':[m['skill_id']],'next_menu_ids':m['next_menu_ids']}
        if m['category_key']=='kuku':payload['available_skill_ids']=['soroban:multiplication']+[f'soroban:kuku:{i}' for i in range(1,10)] if m['mode_kind']!='reading' else ['soroban:multiplication',m['skill_id']]
        elif m['category_key']=='hosu':payload['available_skill_ids']=[m['skill_id'],'soroban:complement:5','soroban:complement:10']
        elif m['category_key']=='anzan':payload['available_skill_ids']=[m['skill_id'],'soroban:mental_addition']+(['soroban:mental_subtraction'] if m['difficulty']!='1' else [])
        elif m['skill_id']=='soroban:advanced':payload['available_skill_ids']=['soroban:add','soroban:sub'] if m['difficulty']=='a1' else ['soroban:mul','soroban:div']
        rows.append({'schema_version':1,'source_app':'soroban','entry_type':'menu','entry_id':m['menu_id'],'content_version':'soroban-material-167','payload':payload})
        skills[m['skill_id']]={'skill_id':m['skill_id'],'label':m['name'] if 'lesson:' in m['skill_id'] else m['skill_id'],
         'parent_skill_id':None,'category_id':m['category_key'],'definition':'既存の出題経路と問題定義に対応する技能。実際の珠操作を観測したという意味ではない。',
         'observation_rule':'自動採点された回答・小段階の回答と支援イベントを別々に参照する。複合問題の誤答を全技能の誤りと断定しない。',
         'prerequisite_skill_ids':None,'progression_group_id':group,'difficulty_axes':['difficulty_id'],'is_active':True}
    for key,label in [('soroban:complement:5','5の補数'),('soroban:complement:10','10の補数'),('soroban:mental_addition','暗算の足し算'),('soroban:mental_subtraction','暗算の引き算'),('soroban:mul','掛け算'),('soroban:div','割り算')]+[(f'soroban:kuku:{i}',f'九九・{i}の段') for i in range(1,10)]:
        skills.setdefault(key,{'skill_id':key,'label':label,'parent_skill_id':None,'category_id':'kuku' if ':kuku:' in key else 'calculation','definition':label,'observation_rule':'問題定義または小段階の回答として記録。最終誤答から原因は断定しない。','prerequisite_skill_ids':None,'progression_group_id':key,'difficulty_axes':[],'is_active':True})
    for row in rows:
        for key in row['payload']['available_skill_ids']:
            skills.setdefault(key,{'skill_id':key,'label':{'soroban:add':'足し算','soroban:sub':'引き算','soroban:mul':'掛け算','soroban:div':'割り算'}.get(key,key),'parent_skill_id':None,'category_id':row['payload']['category_id'],'definition':key,'observation_rule':'対応する問題・小段階の回答から確認する。最終誤答だけでは原因を決めない。','prerequisite_skill_ids':None,'progression_group_id':row['payload']['progression_group_id'],'difficulty_axes':[],'is_active':True})
    for key,p in skills.items():rows.append({'schema_version':1,'source_app':'soroban','entry_type':'skill','entry_id':key,'content_version':'soroban-material-167','payload':p})
    return rows


@st.cache_data(ttl=3600,show_spinner=False)
def cm_publish_menus(version):
    rows=cm_catalog_rows()
    base=''
    try:base=str(st.secrets.get('CHOKOMANA_APP_URL','')).strip()
    except Exception:pass
    from urllib.parse import urlsplit
    if base and (urlsplit(base).scheme!='https' or urlsplit(base).query or urlsplit(base).fragment):base=''
    for r in rows:
        if r['entry_type']=='menu':r['payload']['launch_url']=base
    cm_request('POST','/rest/v1/chokomana_learning_catalog',rows,
        {'on_conflict':'source_app,entry_type,entry_id,content_version'},'resolution=ignore-duplicates,return=minimal')
    return True


def cm_question_catalog(events):
    rows=[]
    for e in events:
        if e['event_type']!='item_presented':continue
        p=e['payload'];snap=p.get('question_snapshot',{})
        # Only canonical educational content; no voice, video or private transcript.
        canonical={k:snap[k] for k in ('a','b','op','terms','operators','answer','quiz','example','events') if k in snap}
        rows.append({'schema_version':1,'source_app':'soroban','entry_type':'question','entry_id':e['question_id'],
         'content_version':e['content_version'],'payload':{'question_id':e['question_id'],
         'question_family_id':p.get('question_family_id'),'skill_ids':p.get('skill_ids'),
         'menu_ids':[p.get('question_family_id')],'difficulty_id':None,'difficulty_axes':p.get('item_settings'),
         'content_hash':hashlib.sha256(json.dumps(canonical,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),
         'assessment_method':p.get('assessment_method'),'response_format':'numeric' if 'quiz' not in snap else 'choice',
         'correct_answer_spec':{'answer':snap.get('answer'),'quiz':snap.get('quiz')},'choice_ids':snap.get('choice_ids'),
         'choice_count':len(snap['quiz']['options']) if snap.get('quiz') else None,'passage_id':None,
         'related_material_id':None,'is_generated':snap.get('op')!='lesson','generator_id':p.get('question_family_id'),
         'generator_version':'soroban-material-167','instance_parameters':canonical,'is_active':True}})
    if rows:cm_request('POST','/rest/v1/chokomana_learning_catalog',rows,{'on_conflict':'source_app,entry_type,entry_id,content_version'},'resolution=ignore-duplicates,return=minimal')


def cm_verify_automatic(events):
    # Verify arithmetic from versioned expression snapshots when they are in this batch.
    snapshots={e['question_id']:e['payload'].get('question_snapshot',{}) for e in events if e['event_type']=='item_presented'}
    for e in events:
        if e['event_type']!='response_submitted':continue
        p=e['payload'];s=snapshots.get(e['question_id'])
        if not s and p.get('substep_id') is None:
            rows=cm_request('GET','/rest/v1/chokomana_learning_catalog',params={'source_app':'eq.soroban','entry_type':'eq.question','entry_id':'eq.'+str(e['question_id']),'content_version':'eq.'+e['content_version'],'select':'payload','limit':'1'})
            if rows:s=rows[0]['payload'].get('instance_parameters')
        if not s or p.get('substep_id') is not None or p.get('response_status')!='answered' or p.get('assessment_method')!='automatic':continue
        try:
            if s.get('quiz'):expected=s['quiz']['answer']
            elif s.get('terms'):
                terms=s['terms'];nums=[t['value'] if isinstance(t,dict) else t for t in terms]
                ops=s.get('operators') or [t.get('op') for t in terms[1:]] if isinstance(terms[0],dict) else s.get('operators') or [s.get('op')]*(len(nums)-1)
                expected=nums[0]
                for op,n in zip(ops,nums[1:]):expected=expected+n if op=='＋' else expected-n if op=='－' else expected*n if op=='×' else expected/n
            elif isinstance(s.get('a'),(int,float)):
                a,b=s['a'],s['b'];op=s.get('op','×');expected=a+b if op=='＋' else a-b if op=='－' else a*b if op=='×' else a/b
            else:continue
            value=p.get('response_value');ok=str(value)==str(expected) or isinstance(value,(int,float)) and value==expected
            if ok is not p['is_correct']:raise StampSaveError('correctness_mismatch')
        except StampSaveError:raise
        except Exception:continue


def process_soroban_stamp_event(event):
    from uuid import UUID
    if not isinstance(event,dict):return False
    token=event.get('device_token','')
    if event.get('identity') is True:
        if st.session_state.get('cm_identity_delivery')==event.get('delivery_id'):return False
        try:
            profile=cm_resolve_identity(token,consume=True);st.session_state['cm_verified_profile']=profile
            st.session_state['cm_link_status']='linked' if profile else 'not_linked'
        except Exception:st.session_state['cm_verified_profile']='';st.session_state['cm_link_status']='unavailable'
        st.session_state['cm_identity_delivery']=event.get('delivery_id');return True
    if not isinstance(event.get('events'),list):return False
    delivery=str(event.get('delivery_id',''))
    try:UUID(delivery)
    except Exception:return False
    if st.session_state.get('soroban_stamp_last_delivery')==delivery:return False
    result={'ok':False,'delivery_id':delivery,'acked':[],'stamp_ok':False}
    try:
        profile=cm_resolve_identity(token);st.session_state['cm_verified_profile']=profile
        events=cm_validate_events(event['events'],profile)
        for row in events:row['event_hash']=hashlib.sha256(json.dumps(row,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
        cm_verify_automatic(events);cm_publish_menus('soroban-material-167');cm_question_catalog(events)
        if events:
            ack=cm_request('POST','/rest/v1/rpc/chokomana_append_soroban_events_v1',{'p_device_hash':cm_device_hash(token),'p_events':events})
            result['acked']=ack.get('acked',[]) if isinstance(ack,dict) else []
        raw=event.get('learning')
        if raw:
            if raw.get('profile_id')!=profile:raise StampSaveError('profile_mismatch')
            menu=next((m for m in CHOKOMANA_MENUS if m['menu_id']==raw.get('menu_id')),None)
            if raw.get('status')=='completed' and menu and menu['mode_kind']=='challenge':
                record=cm_validate_record(raw,profile)
                cm_request('POST','/rest/v1/chokomana_stamps',cm_stamp_row(record,raw.get('grade')),
                    {'on_conflict':'profile_id,source_app,attempt_id'},'resolution=ignore-duplicates,return=minimal')
            result['stamp_ok']=True
        result['ok']=True
    except StampSaveError as e:result['code']=e.code
    except Exception:result['code']='save_failed'
    st.session_state['soroban_stamp_last_delivery']=delivery;st.session_state['soroban_stamp_result']=result;return True


stamp_result=st.session_state.get('soroban_stamp_result')
event=stamp_component(html)(stamp_result=stamp_result,stamp_profile_id=stamp_profile_id(),
    link_status=st.session_state.get('cm_link_status','not_linked'),key='soroban_stamp_board',default=None)
if process_soroban_stamp_event(event):st.rerun()
