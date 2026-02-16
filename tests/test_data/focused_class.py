"""Test fixture for method-level focus analysis."""


class Deck:
    def __init__(self):
        self.cards = []

    def shuffle(self):
        pass

    def deal(self):
        pass


class Game:
    def __init__(self):
        self.deck = Deck()
        self.score = 0

    def play_round(self):
        self.deal_cards()
        self.calculate_score()

    def deal_cards(self):
        self.deck.deal()

    def calculate_score(self):
        self.score += 1

    def reset(self):
        self.score = 0
        self.play_round()


def helper_function():
    game = Game()
    game.play_round()


def logger():
    pass
