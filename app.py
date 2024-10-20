import pandas as pd
import nltk
import praw
from praw.models import MoreComments
from concurrent.futures import ThreadPoolExecutor
nltk.download('punkt')
nltk.download('stopwords')
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
import string
import re
from textblob import TextBlob
import google.generativeai as genai
import os
from dotenv import load_dotenv
from flask import Flask, request, render_template, jsonify
app = Flask(__name__, static_folder='static')
app.secret_key = os.urandom(24)  

# Initialize an empty dictionary to hold uploaded DataFrames
uploaded_data = {}


# load_dotenv()
#API_KEY= os.getenv('API_KEY')
#client_id= os.getenv('client_id')
#client_secret= os.getenv('client_secret')
#user_agent= os.getenv('user_agent')

API_KEY= 'AIzaSyB5FkCO_jtv_2y_6qPAof1z-towKH6DybE'
client_id="X9w8mCZYDlMP_etw5IUq2w"
client_secret="BAd8nxuBlYmxuGBXVpZRKSYa3O5vDQ"
user_agent="windows:Scraper:v1.0.0:(by u/<BestSavings2714>)"

genai.configure(api_key= API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")
file_path = "./amazon.csv"


# LOADING DATA
#def load_data(file_path):
#    try:
#        df = pd.read_csv(file_path)
#        print("Data loaded successfully!")
#        return df
#    except Exception as e:
#        print(f"Error loading file: {e}")
#        return None

reddit = praw.Reddit(
    client_id= client_id,
    client_secret= client_secret,
    user_agent= user_agent
)

# Function to scrape data from Reddit
def fetch_comments(submission, keyword):
    comments = []
    submission.comments.replace_more(limit=None)  # Fetch all comments at once
    for top_level_comment in submission.comments:
        if isinstance(top_level_comment, MoreComments):
            continue
        comments.append({
            'product_name': keyword,
            'review_content': top_level_comment.body,
            'rating': None,  # You can manually add ratings if needed
            'review_title': submission.title,
            'category': submission.subreddit.display_name  # Get the subreddit name
        })
    return comments

def scrape_reddit(keyword, subreddit='BuyItForLife', post_limit=100):
    posts = []
    
    # Search across the specified subreddit or all of Reddit
    submissions = reddit.subreddit(subreddit).search(keyword, limit=post_limit)

    # Use ThreadPoolExecutor for concurrent fetching of comments
    with ThreadPoolExecutor() as executor:
        # Map the fetch_comments function to each submission
        results = list(executor.map(lambda submission: fetch_comments(submission, keyword), submissions))

    # Flatten the list of results
    for result in results:
        posts.extend(result)

    # Convert the data into a DataFrame and save as CSV
    df = pd.DataFrame(posts)
    df.to_csv(f"{keyword}_reviews.csv", index=False)
    print(f"Scraped data saved as {keyword}_reviews.csv")
    if df.empty:
        return jsonify({"message":  "No data found from Reddit for this query."}), 404 
    return df


# PREPROCESSING DATA
def preprocess_data(df):
    df = df[["product_name", "category", "review_content", "rating","review_title"]]
    df.dropna(subset=['review_content'], inplace=True)

    # convert strings to lowercase
    df['cleaned_review']= df['review_content'].apply( lambda x : str.lower(x))
    df['productName']= df['product_name'].apply( lambda x : str.lower(x))
    df['productCategory']= df['category'].apply( lambda x : str.lower(x))
    
    # remove punctuation
    df['cleaned_review'] = df['cleaned_review'].apply(lambda x : " ".join(re.findall(r'\b\w+\b',x)))
    df['productName'] = df['productName'].apply(lambda x : " ".join(re.findall(r'\b\w+\b',x)))
    df['productCategory'] = df['productCategory'].apply(lambda x : " ".join(re.findall(r'\b\w+\b',x)))
    stop_words = set(stopwords.words('english'))

    # removing stopwords
    def remove_stopWords(s):
        '''For removing stop words
        '''
        s = ' '.join(word for word in s.split() if word not in stop_words)
        return s
    df['cleaned_review'] = df['cleaned_review'].apply(lambda x: remove_stopWords(x))
    df['productName'] = df['productName'].apply(lambda x: remove_stopWords(x))
    df['productCategory'] = df['productCategory'].apply(lambda x: remove_stopWords(x))
    return df

# FILTERING REVIEWS (user input based)
def filter_reviews(df, user_input):
    count= len(user_input.split())   # count the number of words in input
    if count>1:                      # Regex matching for >1 word
        from sklearn.metrics.pairwise import cosine_similarity
        import numpy as np
        import re 
            # Function to create a regex pattern for multi-word matches
        def regex_match(input_text, entity_list):
                # Create a pattern that allows for optional words between product terms
                pattern = re.sub(r"\s+", r".*", input_text.lower())  # "boat headphones" becomes "boat.*headphones"
                for entity in entity_list:
                    if re.search(pattern, entity.lower()):
                        return entity
                return None
        matched_rows = []
        for idx, row in df.iterrows():
            product_name = row['productName']    
            entity_list = [product_name]               # Use productName as the entity list
            # Apply regex matching
            match = regex_match(user_input, entity_list)
            if match:
                matched_rows.append(row) 
                
        filtered_df = pd.DataFrame(matched_rows)       # Convert matched rows to a DataFrame
        if filtered_df.empty:                          
            print(f"No reviews found for {user_input} using regex matching.")
        else:
            print(f"Found {len(filtered_df)} reviews for {user_input} using regex matching.")
        return filtered_df
    else:                                              # single word input recieved
        filtered_df = df[(df['productName'].str.contains(user_input, case=False, na=False)) | 
          (df['productCategory'].str.contains(user_input, case=False, na=False))]
        if filtered_df.empty:
            print(f"No reviews found for {user_input}.")
        else:
            print(f"Found {len(filtered_df)} reviews for {user_input}.")
            return filtered_df  
    if len(filtered_df) == 0:
        return jsonify({"message": "No reviews found"}), 404  # Send a 404 status code
    # If reviews exist, return them as normal
    return jsonify({"reviews": filtered_df})  

# SENTIMENT ANALYSIS
def classify_sentiment(text):
        from textblob import TextBlob
        blob = TextBlob(text)
        polarity = blob.sentiment.polarity
        # Classify the sentiment
        if polarity > 0:
            return 'Positive'
        elif polarity < 0:
            return 'Negative'
        else:
            return 'Neutral'

# CORPUS SUMMARIZATION BASED ON INPUT LENGTH
def summarize_corpus(corpus_text, length):  
    prompt = f"Summarize these reviews concisely in {length} words in a paragraph: {corpus_text}."
    response = model.generate_content(prompt)
    return response.text

# FINAL DATA PROCESSING

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.route('/summarize', methods=['POST'])
def summarize():
    if request.method == "POST":
        user_input = request.form['user_input']
        length= int(request.form['input_length']) 
        
       # subreddit= request.form['subreddit'].strip()
       # if not subreddit:
       #     subreddit="BuyItForLife"
        df= pd.read_csv(file_path)
        df = preprocess_data(df)
        text= filter_reviews(df, user_input)
        # review_count= len(text)
        # Perform sentiment analysis on each review by creating a new column sSentiment'
        text['sentiment'] = text['cleaned_review'].apply(classify_sentiment)
        # filter positive reviews
        positive_reviews = text[text['sentiment'] == 'Positive']['cleaned_review'].tolist()
        # Filter negative reviews
        negative_reviews = text[text['sentiment'] == 'Negative']['cleaned_review'].tolist()
        positive_corpus = ' '.join(positive_reviews)
        negative_corpus = ' '.join(negative_reviews)
        # Get the summaries for the entire corpus
        positive_summary = summarize_corpus(positive_corpus, length) if positive_reviews else 'No reviews found'
        negative_summary = summarize_corpus(negative_corpus, length) if negative_reviews else 'No reviews found'
        # Print the summaries
        print("Positive Reviews Summary:\n", positive_summary)
        print("\nNegative Reviews Summary:\n", negative_summary)
        return jsonify({'positive_summary': positive_summary, 'negative_summary': negative_summary })

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

    
      