"""Keep presentation tests independent of the user's saved application locale."""

import pytest

from i18n import set_language


@pytest.fixture(autouse=True)
def isolate_application_language():
    # A workbench test may load the user's real saved locale. Do not let that
    # leak into subsequent tests whose default-language expectations are Chinese.
    # Individual i18n tests remain free to select English or Japanese.
    set_language("zh-CN")
    yield
    set_language("zh-CN")
