import tempfile

from django.test import override_settings
from django.test.runner import DiscoverRunner


class LocalTestRunner(DiscoverRunner):
    """Las imágenes de pruebas nunca se mezclan con django/media del usuario."""

    def setup_test_environment(self, **kwargs):
        self.media = tempfile.TemporaryDirectory(prefix="butaca-tests-")
        self.local_media = override_settings(MEDIA_ROOT=self.media.name)
        self.local_media.enable()
        try:
            super().setup_test_environment(**kwargs)
        except BaseException:
            self.local_media.disable()
            self.media.cleanup()
            raise

    def teardown_test_environment(self, **kwargs):
        try:
            super().teardown_test_environment(**kwargs)
        finally:
            self.local_media.disable()
            self.media.cleanup()
