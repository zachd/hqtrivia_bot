""" utilities for the HQ Trivia bot project """
import re
import sys
from enum import Enum
import urllib.parse
import webbrowser
import grequests
from requests_cache import CachedSession
from nltk.corpus import stopwords
from bs4 import BeautifulSoup


class Colours(Enum):
    """ console colours """
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


class Weights(Enum):
    """ weights for each algorithm """
    GOOGLE_SUMMARY_ANSWER_COUNT = 200
    GOOGLE_RESULTS_NUMBER = 100
    WIKIPEDIA_PAGE_QUESTION_COUNT = 100


def build_answers(raw_answers):
    """" Build set of answers from raw data """
    answers = {
        'A': raw_answers[0]['text'],
        'B': raw_answers[1]['text'],
        'C': raw_answers[2]['text']
    }
    return answers


def build_google_queries(question, answers, session=None):
    """" Build google query set from data and options """
    queries = [question]
    queries += ['%s "%s"' % (question, answer) for answer in answers.values()]
    return [grequests.get('https://www.google.co.uk/search?q=' + urllib.parse.quote_plus(q),
                          session=session) for q in queries]


def build_wikipedia_queries(_question, answers, session=None):
    """ Build wikipedia query set from data and options """
    queries = list(answers.values())
    return [grequests.get('https://en.wikipedia.org/wiki/Special:Search?search=' + urllib.parse.quote_plus(q),
                          session=session) for q in queries]


def predict_answers(question):
    """ Get answer predictions """
    confidence = {
        'A': 0,
        'B': 0,
        'C': 0
    }

    if not question.is_replay:
        webbrowser.open("http://google.com/search?q="+question.text)

    print('\n\n\n\n\n')
    print('------------ %s %s | %s ------------' % ('QUESTION', question.number, question.category))
    print(Colours.BOLD.value + question.text + Colours.ENDC.value)
    print('------------ %s ------------' % 'ANSWERS')
    print(question.answers)
    print('------------------------')
    print('\n')

    session = CachedSession('query_cache') if question.is_replay else None
    google_responses = grequests.map(build_google_queries(question.text, question.answers, session))
    wikipedia_responses = grequests.map(build_wikipedia_queries(question.text, question.answers, session))

    confidence = find_answer_words_google(question.text, question.answers, confidence, google_responses[:1])
    confidence = count_results_number_google(question.text, question.answers, confidence, google_responses[1:])
    confidence = find_question_words_wikipedia(question.text, question.answers, confidence, wikipedia_responses)

    # Calculate prediction
    if 'NOT' in question.text or 'NEVER' in question.text:
        prediction = min(confidence, key=confidence.get)
    else:
        prediction = max(confidence, key=confidence.get)
    total_occurrences = sum(confidence.values())
    for index, count in confidence.items():
        likelihood = int(count/total_occurrences * 100) if total_occurrences else 0
        confidence[index] = '%d%%' % likelihood
        result = 'Answer %s: %s - %s%%' % (index, question.answers[index], likelihood)
        print(Colours.BOLD.value + result + Colours.ENDC.value if index == prediction else result)

    print('\n')
    return prediction if confidence[prediction] else None, confidence


def find_answer_words_google(_question, answers, confidence, responses):
    """ METHOD 1: Find answer in Google search result descriptions """
    occurrences = {'A': 0, 'B': 0, 'C': 0}
    response = responses[0]
    soup = BeautifulSoup(response.text, "html5lib")

    # Check for rate limiting page
    if '/sorry/index?continue=' in response.url:
        sys.exit('ERROR: Google rate limiting detected.')

    results = ''
    # Get search descriptions
    for element in soup.find_all(class_='st'):
        results += " " + element.text
    # Get search titles
    for element in soup.find_all(class_='r'):
        results += " " + element.text
    # Get search result card
    for element in soup.find_all(class_='mod'):
        results += " " + element.text
    # Get related search results card
    for element in soup.find_all(class_='brs_col'):
        results += " " + element.text
    cleaned_results = results.strip().replace('\n', '')
    results_words = get_raw_words(cleaned_results)

    # Find answer words in search descriptions
    for index, answer in answers.items():
        answer_words = get_raw_words(answer)
        occurrences[index] += results_words.count(answer_words)

    print("Count: %s%s%s" % (Colours.BOLD.value, occurrences, Colours.ENDC.value))

    # Calculate confidence
    total_occurrences = sum(occurrences.values())
    for index, count in occurrences.items():
        if total_occurrences:
            confidence[index] += int(count / total_occurrences * Weights.GOOGLE_SUMMARY_ANSWER_COUNT.value)

    print("METHOD 1 - Confidence: %s\n" % confidence)
    return confidence


def count_results_number_google(_question, _answers, confidence, responses):
    """ METHOD 2: Compare number of results found by Google """
    occurrences = {'A': 0, 'B': 0, 'C': 0}

    # Loop through search results
    for index, response in enumerate(responses):
        soup = BeautifulSoup(response.text, "html5lib")
        if soup.find(id='resultStats'):
            results_count_text = soup.find(id='resultStats').text.replace(',', '')
            results_count = re.findall(r'\d+', results_count_text)[0]
            occurrences[chr(65 + index)] += int(results_count)

    print("Search Results: %s%s%s" % (Colours.BOLD.value, occurrences, Colours.ENDC.value))

    # Calculate confidence
    total_occurrences = sum(occurrences.values())
    for index, count in occurrences.items():
        if total_occurrences:
            confidence[index] += int(count / total_occurrences * Weights.GOOGLE_RESULTS_NUMBER.value)

    print("METHOD 1 + 2 - Confidence: %s\n" % confidence)
    return confidence


def find_question_words_wikipedia(question, _answers, confidence, responses):
    """ METHOD 3: Find question words in wikipedia pages """
    occurrences = {'A': 0, 'B': 0, 'C': 0}

    # Get nouns from question words

    question_nouns = get_significant_words(get_raw_words(question))

    # Loop through wikipedia results
    for index, response in enumerate(responses):

        # Check for unresolved Wikipedia link
        if 'Special:Search' in response.url:
            print('METHOD 3 - SKIPPED: Unresolved Wikipedia link\n')
            return confidence

        # Get wikipedia page text elements
        results = ''
        soup = BeautifulSoup(response.text, "html5lib")
        for element in soup.find_all('p'):
            results += " " + element.text
        cleaned_results = results.strip().replace('\n', '')
        results_words = get_raw_words(cleaned_results)

        # Find question words on wikipedia page
        occurrences_list = find_keywords(question_nouns, results_words)
        occurrences[chr(65 + index)] += sum(occurrences_list)

    # Calculate confidence
    total_occurrences = sum(occurrences.values())
    for index, count in occurrences.items():
        if total_occurrences:
            confidence[index] += int(count / total_occurrences * Weights.WIKIPEDIA_PAGE_QUESTION_COUNT.value)

    print("METHOD 1 + 2 + 3 - Confidence: %s\n" % confidence)
    return confidence


def find_keywords(keywords, data):
    """ Find keywords in specified data """
    words_found = []
    for keyword in keywords:
        if len(keyword) > 2:
            if keyword in data and keyword not in words_found:
                words_found.append(data.count(keyword))
    return words_found


def get_significant_words(question_words):
    """ Returns a list of the words from the input string that are not in NLTK's stopwords """
    our_stopwords = set(stopwords.words('english'))
    return list(filter(lambda word: word not in our_stopwords, question_words.split(' ')))


def get_raw_words(data):
    """ Extract raw words from data """
    data = re.sub(r'[^\w ]', '', data).replace(' and ', ' ')
    words = data.replace('  ', ' ').lower()
    return words
