# epub_filter_tool
a tool to find genres associated with epubs by searching goodreads, with a simple GUI to sort them once processed

This code is currently a WIP.

No provided requirements.txt yet, will include when the script is improved.

The overall flow is as follows, broken up into 2 scripts -

# grsearch.py
1. User input for the folder of .epubs to process
2. A LLM cleans up filenames, and a sanitization function cleans up any extra punctuation
3. The cleaned up filenames are passed to automated Chrome windows with a GoodReads search URL
4. The search page is checked for results, and the book page URL and amount of ratings are parsed
5. If there are less than 500 ratings, a txt file matching the original epub filename is saved with the text "unpopular" and any further processing for that book is skipped.
6. If there is no book found, a txt file with "unknown" is saved for the book and the genre logic is skipped.
7. Once the book is found, it navigates to the book page to find the genres, and saves them to a text file.
8. Once the entire is folder is processed, another folder path can be entered.
   
Note - It is set up to process 10 books at a time. It runs ok on my beefy PC, but if you run into any performance issues, reduce the 10s in process_folder to a lower value.

# sortgui.py
1. Browse for a folder that has been processed by grsearch.py and load the epub and txt files
2. Sort by genre and view books associated with the selected genre
3. Type to search/filter box
4. Button to delete currently filtered books
5. Button to move currently filtered books to a folder with the genre name

![sortgui](https://github.com/secretlycarl/epub_filter_tool/blob/main/sortgui/sortgui.png)

# Things to Work On
- I want to combine the two scripts into one to make the install process and general use easier

# Note
Making thousands of requests to GoodReads servers is going to get you rate limited/temp banned for a day or so. I'm working on a way to find when this happens so it doesn't just save "unknown" to a bunch of files when it shouldn't.
