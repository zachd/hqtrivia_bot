import re
import sys
from nltk.corpus import stopwords
import requests_cache
import grequests
import urllib.parse
import webbrowser
from bs4 import BeautifulSoup

class colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

class weights:
    GOOGLE_SUMMARY_ANSWER_COUNT = 200
    NUM_GOOGLE_RESULTS = 100
    WIKIPEDIA_PAGE_QUESTION_COUNT = 100

# Build set of answers from raw data
def build_answers(raw_answers):
    answers = {
        'A': raw_answers[0]['text'],
        'B': raw_answers[1]['text'],
        'C': raw_answers[2]['text']
    }
    return answers


# Build google query set from data and options
def build_google_queries(question, answers, session):
    queries = [question]
    queries += ['%s "%s"' % (question, answer) for answer in answers.values()]

    return [grequests.get('https://www.google.co.uk/search?q=' + urllib.parse.quote_plus(q), session=session) for q in queries]


# Build wikipedia query set from data and options
def build_wikipedia_queries(question, answers, session):
    queries = list(answers.values())

    return [grequests.get('https://en.wikipedia.org/wiki/Special:Search?search=' + urllib.parse.quote_plus(q), session=session) for q in queries]


# Get answer predictions
def predict_answers(data, answers):

    confidence = {
        'A': 0,
        'B': 0,
        'C': 0
    }
    question = data.get('question')

    if not data.get('is_testing', False):
        webbrowser.open("http://google.com/search?q="+question)

    print('\n\n\n\n\n')
    print('------------ %s %s | %s ------------' % ('QUESTION', data.get('questionNumber'), data.get('category')))
    print(colors.BOLD + question + colors.ENDC)
    print('------------ %s ------------' % 'ANSWERS')
    print(answers)
    print('------------------------')
    print('\n')

    session = requests_cache.CachedSession('query_cache') if data.get('is_testing', False) else None
    google_responses = grequests.map(build_google_queries(question, answers, session))
    wikipedia_responses = grequests.map(build_wikipedia_queries(question, answers, session))

    confidence = find_answer_words_google(question, answers, confidence, google_responses[:1])
    confidence = count_results_number_google(question, answers, confidence, google_responses[1:])
    confidence = find_question_words_wikipedia(question, answers, confidence, wikipedia_responses)

    # Calculate prediction
    prediction = min(confidence, key=confidence.get) if 'NOT' in question or 'NEVER' in question else max(confidence, key=confidence.get)
    total_occurrences = sum(confidence.values())
    for n, count in confidence.items():
        likelihood = int(count/total_occurrences * 100) if total_occurrences else 0
        confidence[n] = '%d%%' % likelihood
        result = 'Answer %s: %s - %s%%' % (n, answers[n], likelihood)
        print(colors.BOLD + result + colors.ENDC if n == prediction else result)

    print('\n')
    return (prediction if confidence[prediction] else None, confidence)


# METHOD 1: Find answer in Google search result descriptions
def find_answer_words_google(question, answers, confidence, responses):

    occurrences = {'A': 0, 'B': 0, 'C': 0}
    response = responses[0]
    soup = BeautifulSoup(response.text, "html5lib")

    # Check for rate limiting page
    if '/sorry/index?continue=' in response.url:
        sys.exit('ERROR: Google rate limiting detected.')

    results = ''
    # Get search descriptions
    for g in soup.find_all(class_='st'):
        results += " " + g.text
    # Get search titles
    for g in soup.find_all(class_='r'):
        results += " " + g.text
    cleaned_results = results.strip().replace('\n','')
    results_words = get_raw_words(cleaned_results)

    # Find answer words in search descriptions
    for n, answer in answers.items():
        answer_words = get_raw_words(answer)
        occurrences[n] += results_words.count(answer_words)

    print("Count: %s%s%s" % (colors.BOLD, occurrences, colors.ENDC))

    # Calculate confidence
    total_occurrences = sum(occurrences.values())
    for n, count in occurrences.items():
        confidence[n] += int(count/total_occurrences * weights.GOOGLE_SUMMARY_ANSWER_COUNT) if total_occurrences else 0

    print("METHOD 1 - Confidence: %s\n" % confidence)
    return confidence


# METHOD 2: Compare number of results found by Google
def count_results_number_google(question, answers, confidence, responses):

    occurrences = {'A': 0, 'B': 0, 'C': 0}

    # Loop through search results
    for n, response in enumerate(responses):
        soup = BeautifulSoup(response.text, "html5lib")
        if soup.find(id='resultStats'):
            results_count_text = soup.find(id='resultStats').text.replace(',', '')
            results_count = re.findall(r'\d+', results_count_text)[0]
            occurrences[chr(65 + n)] += int(results_count)

    print("Search Results: %s%s%s" % (colors.BOLD, occurrences, colors.ENDC))

    # Calculate confidence
    total_occurrences = sum(occurrences.values())
    for n, count in occurrences.items():
        confidence[n] += int(count/total_occurrences * weights.NUM_GOOGLE_RESULTS) if total_occurrences else 0

    print("METHOD 1 + 2 - Confidence: %s\n" % confidence)
    return confidence


# METHOD 3: Find question words in wikipedia pages
def find_question_words_wikipedia(question, answers, confidence, responses):

    occurrences = {'A': 0, 'B': 0, 'C': 0}

    # Get nouns from question words
    question_words = get_raw_words(question)
    question_nouns = get_significant_words(question_words)

    # Loop through wikipedia results
    for n, response in enumerate(responses):

        # Check for unresolved Wikipedia link
        if 'Special:Search' in response.url:
            print('METHOD 3 - SKIPPED: Unresolved Wikipedia link\n')
            return confidence

        # Get wikipedia page text elements
        results = ''
        soup = BeautifulSoup(response.text, "html5lib")
        for g in soup.find_all('p'):
            results += " " + g.text
        cleaned_results = results.strip().replace('\n','')
        results_words = get_raw_words(cleaned_results)

        # Find question words on wikipedia page
        occurrences_list = find_keywords(question_nouns, results_words)
        occurrences[chr(65 + n)] += sum(occurrences_list)

    # Calculate confidence
    total_occurrences = sum(occurrences.values())
    for n, count in occurrences.items():
        confidence[n] += int(count/total_occurrences * weights.WIKIPEDIA_PAGE_QUESTION_COUNT) if total_occurrences else 0

    print("METHOD 1 + 2 + 3 - Confidence: %s\n" % confidence)
    return confidence


# Find keywords in specified data
def find_keywords(keywords, data):
    words_found = []
    for keyword in keywords:
        if len(keyword) > 2:
            if keyword in data and keyword not in words_found:
                words_found.append(data.count(keyword))
    return words_found


# Returns a list of the words from the input string that are not in NLTK's stopwords
def get_significant_words(input):
    s=set(stopwords.words('english'))
    return list(filter(lambda w: not w in s, input.split(' ')))


# Extract raw words from data
def get_raw_words(data):
    data = re.sub('[^\w ]', '' , data).replace(' and ',' ')
    words = data.replace('  ' , ' ').lower()
    return words
