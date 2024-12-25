# epub_filter_tool
a tool to find genres associated with epubs by searching goodreads, with a simple GUI to sort them once processed

This code is currently a WIP. It works, but with some limitations/inefficiencies. 

The overall flow is as follows, broken up into 2 scripts -

# grsearch.py
1. User input for the folder of .epubs to process
2. A LLM cleans up filenames, and a sanitization function cleans up any extra punctuation
3. The cleaned up filenames are passed to automated Chrome windows with a GoodReads search URL
4. The search page is checked for results, and the book page URL and amount of ratings are parsed
5. If there are less than 500 ratings, a txt file matching the original epub filename is saved with the text "unpopular" and any further processing for that book is skipped.
6. If there is no book found, a txt file '                                                                  ' "unknown" '                                                  '.
7. Once the book is found, it navigates to the book page to find the genres, and saves them to a text file.
8. Once the entire is folder is processed, another folder path can be entered.
   Note - It is set up to process 10 books at a time

# sortgui.py
1. Browse for a folder that has been processed by grsearch.py and load the epub and txt files
2. Sort by genre and view books associated with the selected genre
3a. Button to delete currently filtered books
3b. Button to move currently filtered books to a folder with the genre name

# Things to Work On
I don't think my implementation of selenium with the webdriver and beautifulsoup are as efficient as they can be, and its supposed to be headless but I can't get it to stop opening windows.
- The pages load very quickly, but the script takes a while to parse the webpages for the content I want. It takes about 5hr to process 1000 books.
- I want to combine the two scripts into one to make the install process and general use easier

