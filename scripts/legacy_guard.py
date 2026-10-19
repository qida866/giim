"""旧版批处理保留用于历史复现，生产仅允许新流水线写入。"""
import os


def allow_legacy_mutation() -> bool:
    allowed = os.getenv('APP_ENV', 'dev') not in {'production', 'prod'} and os.getenv('GIIM_ALLOW_LEGACY_MUTATION') == 'true'
    if not allowed:
        print('Legacy mutation disabled. Use scripts.pipeline or scripts.reconcile_vectors --repair. For historical reproduction only, back up first and set GIIM_ALLOW_LEGACY_MUTATION=true in development.')
    return allowed
