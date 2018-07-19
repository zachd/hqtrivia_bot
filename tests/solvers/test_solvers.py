""" unit tests for solvers """
import pytest
from mock import Mock
from solvers import GoogleAnswerWordsSolver, GoogleResultsCountSolver

@pytest.fixture
def api_response():
    """ question/answers example set """
    return {
        "answers": {
            "A": "Badger",
            "B": "Cheetah",
            "C": "Giraffe"
        },
        "category": "Nature",
        "is_replay": True,
        "question": "What is the world's fastest land animal?",
        "questionId": 28482,
        "questionNumber": 1
    }

def test_google_answer_words_run(api_response): # pylint: disable=redefined-outer-name
    """ testing run """

    mock_response = Mock()
    mock_response.url = "/"
    mock_response.text = "Example Response"

    mock_session = Mock()
    mock_session.get.return_value.result.return_value = mock_response

    (prediction, confidence) = GoogleAnswerWordsSolver().run(
        api_response.get('question'), api_response.get('answers'), mock_session, {'A': 0, 'B': 0, 'C': 0}
    )

    assert prediction == 'A'
    assert confidence == {'A': 0, 'B': 0, 'C': 0}


def test_google_results_count_run(api_response): # pylint: disable=redefined-outer-name
    """ testing run """

    mock_response = Mock()
    mock_response.url = "/"
    mock_response.text = "Example Response"

    mock_session = Mock()
    mock_session.get.return_value.result.return_value = mock_response

    (prediction, confidence) = GoogleResultsCountSolver().run(
        api_response.get('question'), api_response.get('answers'), mock_session, {'A': 0, 'B': 0, 'C': 0}
    )

    assert prediction == 'A'
    assert confidence == {'A': 0, 'B': 0, 'C': 0}
