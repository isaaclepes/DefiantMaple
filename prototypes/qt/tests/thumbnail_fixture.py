"""Account-independent admission and managed-cache authority for generated Qt fixtures."""
import sys
from unittest.mock import patch

from defiantmaple import admission


def isolate_thumbnail_authority(test, database, root):
    """Install before any public cache call; unwind after window/worker cleanup."""
    registry = root / 'admission'
    registry_patch = patch.object(admission, 'registry_path', return_value=registry)
    registry_patch.start()
    test.addCleanup(registry_patch.stop)
    if sys.platform == 'linux':
        from defiantmaple import linux_thumbnails
        for name, value in (('default_authority_root', root / 'authority'),
                            ('registry_path', registry)):
            authority_patch = patch.object(linux_thumbnails, name, return_value=value)
            authority_patch.start()
            test.addCleanup(authority_patch.stop)
    owner_context = admission.admission_session(database, _registry_path=registry)
    owner = owner_context.__enter__()
    test.addCleanup(owner_context.__exit__, None, None, None)
    return owner
