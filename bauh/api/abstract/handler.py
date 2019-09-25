from typing import List

from bauh.api.abstract.view import MessageType, ViewComponent


class ProcessWatcher:
    """
    Represents an view component watching background processes. It's a bridge for ApplicationManager instances notifiy the view of processes progression and also
    request any user interaction without the need of knowing any GUI code.
    """

    def print(self, msg: str):
        """
        prints a given message to the user. In the current GUI implementation, the message is printed on the terminal window ("Details")
        :param msg:
        :return:
        """
        pass

    def request_confirmation(self, title: str, body: str, components: List[ViewComponent] = None, confirmation_label: str = None, deny_label: str = None)-> bool:
        """
        request a user confirmation. In the current GUI implementation, it shows a popup to the user.
        :param title: popup title
        :param body: popup body
        :param components: extra view components that will be rendered to the confirmation popup.
        :param confirmation_label: optional confirmation button label (default to 'yes')
        :param deny_label: optional deny button label (default to 'no')
        :return: if the request was confirmed by the user
        """
        pass

    def show_message(self, title: str, body: str, type_: MessageType = MessageType.INFO):
        """
        shows a message to the user. In the current GUI implementation, it shows a popup.
        :param title:
        :param body:
        :param type_: determines the icon that will be displayed
        :return:
        """
        pass

    def change_status(self, msg: str):
        """
        Changes the process status. In the current GUI implementation, the process status is displayed above the toolbar.
        :param msg: msg
        :return:
        """
        pass

    def change_substatus(self, msg: str):
        """
        Changes the process substatus. In the current GUI implementation, the process substatus is displayed above the progress bar.
        :param msg:
        :return:
        """

    def change_progress(self, val: int):
        """
        Changes the process progress. In the current GUI implementation, the progress is displayed as a bottom bar.
        :param val: a val between 0 and 100
        :return:
        """

    def should_stop(self) -> bool:
        """
        :return: if the use requested to stop the process.
        """
