from typing import List, Tuple, Optional

from bauh.api.abstract.view import MessageType, ViewComponent


class ProcessWatcher:
    """
    Represents an view component watching background processes. It's a bridge for ApplicationManager instances notify the view of processes progression and also
    request any user interaction without the need of knowing any GUI code.
    """

    def print(self, msg: str):
        """
        prints a given message to the user. In the current GUI implementation, the message is printed on the terminal window ("Details")
        :param msg:
        :return:
        """
        pass

    def request_confirmation(self, title: str, body: Optional[str], components: List[ViewComponent] = None, confirmation_label: str = None,
                             deny_label: str = None, deny_button: bool = True, window_cancel: bool = False,
                             confirmation_button: bool = True) -> bool:
        """
        request a user confirmation. In the current GUI implementation, it shows a popup to the user.
        :param title: popup title
        :param body: popup body
        :param components: extra view components that will be rendered to the confirmation popup.
        :param confirmation_label: optional confirmation button label (default to 'yes')
        :param deny_label: optional deny button label (default to 'no')
        :param deny_button: if the deny button should be displayed
        :param window_cancel: if the window cancel button should be visible
        :param confirmation_button: if the confirmation button should be displayed
        :return: if the request was confirmed by the user
        """
        pass

    def request_reboot(self, msg: str) -> bool:
        """
        :return: requests a system reboot
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

    def request_root_password(self) -> Tuple[bool, str]:
        """
        asks the root password for the user
        :return: a tuple informing if the password is valid and its text
        """


class TaskManager:

    def register_task(self, id_: str, label: str, icon_path: str):
        """
        :param id_: an unique identifier for the task
        :param label: an i18n label
        :param icon_path: str
        :return:
        """
        pass

    def update_progress(self, task_id: str, progress: float, substatus: Optional[str]):
        """
        :param task_id:
        :param progress: a float between 0 and 100.
        :param substatus: optional substatus string representing the current state
        :return:
        """
        pass

    def update_output(self, task_id: str, output: str):
        """
        updates the task output
        :param task_id:
        :param output:
        :return:
        """
        pass

    def finish_task(self, task_id: str):
        """
        marks a task as finished
        :param task_id:
        :return:
        """
        pass
