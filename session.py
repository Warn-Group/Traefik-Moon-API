from random import randint
from typing import Self

class Session():
    sessions: list[Self] = []

    def __init__(self, dummy: bool = False) -> None:
        if not dummy:
            self.code: str = self.__assign_random_code()
            self.sessions.append(self)

    def __repr__(self) -> str:
        return f"<Session: {self.code}>"

    def __create_random_code(self) -> str:
        return f"{randint(16, 2**128):032x}"

    def __assign_random_code(self) -> str:
        temp_code = self.__create_random_code()
        if temp_code in [session.code for session in self.sessions]:
            return self.__assign_random_code()
        return temp_code

    def remove(self):
        self.sessions.remove(self)

    def get_by_code(self, code: str):
        for session in self.sessions:
            if session.code == code:
                return session
        return None