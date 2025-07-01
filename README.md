# epub_filter_tool
A tool to find genres associated with epubs by searching goodreads, with a simple GUI to sort and process them.

# Windows Install
```
git clone https://github.com/secretlycarl/epub_filter_tool

cd epub_filter_tool

python -m venv venv

.\venv\Scripts\activate

pip install -r requirements.txt

python main.py
```

This is the basic flow of the script -

# main.py
1. User input for the folder of .epubs to process
2. A LLM cleans up filenames, and a sanitization function cleans up any extra punctuation
3. The cleaned up filenames are passed to HTTP requests with a GoodReads search URL
4. The search page is checked for results, and the book page URL and amount of ratings are parsed
5. If there are less than 500 ratings, a txt file matching the original epub filename is saved with the text "unpopular" and any further processing for that book is skipped.
6. If there is no book found, a txt file with "unknown" is saved for the book and the genre logic is skipped.
7. Once the book is found, it navigates to the book page to find the genres, and saves them to a text file.
8. Once the entire is folder is processed, another folder path can be entered.
   
Note - It is set up to process 20 books at a time. It runs ok on my beefy PC, but if you run into any performance issues or rate limiting, reduce ```BATCH_SIZE``` near the top to a lower value.

# GUI
1. Sort by genre and view books associated with the selected genre
2. Type to search/filter box
3. Button to delete currently filtered books
4. Button to move currently filtered books to a folder with the genre name
5. The UI updates as books are processed. If you open a folder that has already been processed, click "Update" to load in the list of genre tags.

![sortgui](https://github.com/secretlycarl/epub_filter_tool/blob/main/gui-screenshot.png)

# Things to Work On
- Try to implement a more lightweight LLM. The current model is ~8GB so a graphics card with at least that much VRAM is needed

# Note
Making thousands of requests to GoodReads servers might get you rate limited/temp banned for a day or so. I can do 3k books/day without issue but it happened once in my testing with more than 5k books.
