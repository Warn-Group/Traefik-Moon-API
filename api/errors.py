class CodeErrors:
    def __init__(self) -> None:
        self.lexer = None
        self.parser = None
        self.execution = None

    @property
    def has_errors(self):
        if self.lexer or self.parser or self.execution:
            return True
        return False
    
    def __str__(self) -> str:
        return f"Syntax error(s): {self.lexer}"