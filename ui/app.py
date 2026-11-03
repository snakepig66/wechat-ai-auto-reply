"""Final AppGUI composition."""

import logging

from .theme import *

logger = logging.getLogger(__name__)


from .base import AppGUIBase
from .console import ConsoleTabMixin
from .floating import FloatingMixin
from .preview import ReplyPreviewMixin
from .send import SendTabMixin
from .settings import SettingsTabMixin
from .style_tab import StyleTabMixin
from .worker import WorkerMixin


class AppGUI(AppGUIBase, FloatingMixin, ConsoleTabMixin, SendTabMixin,
              SettingsTabMixin, StyleTabMixin, ReplyPreviewMixin,
              WorkerMixin):
    """Main GUI combining all feature mixins."""
