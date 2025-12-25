from contextvars import ContextVar

# ここで「コンテキスト」を定義します。
# 'trace_id' はコンテキストの名前、default='N/A'は何も入っていない時のデフォルト値です。
trace_id_var: ContextVar[str] = ContextVar('trace_id', default='N/A')