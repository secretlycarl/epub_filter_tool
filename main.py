import os
import tkinter as tk
from tkinter import filedialog
from tkinter import messagebox
from tkinter import ttk
from concurrent.futures import ThreadPoolExecutor
import re
import urllib.parse
import aiohttp
import asyncio
import threading
from bs4 import BeautifulSoup, SoupStrainer
from transformers import AutoModelForCausalLM, AutoProcessor

# Model setup
model_id = "microsoft/Phi-3.5-vision-instruct"
model = AutoModelForCausalLM.from_pretrained(
    model_id, 
    device_map="cuda", 
    trust_remote_code=True, 
    torch_dtype="auto", 
    _attn_implementation='eager'    
)
processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)

def clean_filename_with_llm(filename):
    """Use LLM to clean up the filename."""
    system_prompt = (
        "This is a filename, please clean it up. Your output should be in the format of [title] [author name]. "
        "You will remove any punctuation and symbols except for periods, replace any double spaces with a single space, "
        "and remove any non-title or author name words. Examples - "
        '"A Christmas Carol (NOVEL, 2012, v. 1  IN GREEK) (Greek Edition) - KONDYLIS, THANOS.epub" becomes '
        '"A Christmas Carol Thanos Kondylis". '
        '"a to Z of Girlfriends, The - Natasha West.epub" becomes "The a to Z of Girlfriends Natasha West".'
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Filename: {filename}"}
    ]

    prompt = processor.tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True
    )

    inputs = processor(prompt, return_tensors="pt").to("cuda:0")

    generation_args = {
        "max_new_tokens": 1000,
        "temperature": 0.0,
        "do_sample": False,
    }

    generate_ids = model.generate(**inputs,
                                  eos_token_id=processor.tokenizer.eos_token_id,
                                  **generation_args)

    # Remove input tokens
    generate_ids = generate_ids[:, inputs['input_ids'].shape[1]:]
    response = processor.batch_decode(generate_ids,
                                      skip_special_tokens=True,
                                      clean_up_tokenization_spaces=False)[0]
    return response.strip()

def sanitize_filename(filename):
    """Sanitize filenames for better search terms."""
    sanitized = filename.replace(".epub", "")
    sanitized = re.sub(r"[!\"#$%&'()*+,/:;<=>?@[\\]^_`{|}~]", "", sanitized)
    sanitized = sanitized.replace("'", "")
    sanitized = re.sub(r"[\[\](){}]", "", sanitized)
    sanitized = sanitized.replace(" - ", " ")
    sanitized = sanitized.replace("- ", " ")
    return sanitized

def process_single_file(filename, directory):
    """Process a single file: clean with LLM, sanitize, and search Goodreads."""
    cleaned_filename = clean_filename_with_llm(filename)
    sanitized_filename = sanitize_filename(cleaned_filename)
    return filename, sanitized_filename, directory

def save_genres_to_file(original_filename, genres, directory):
    """Save the genres or status message to a txt file in the same directory as the epub."""
    base_filename = os.path.splitext(original_filename)[0]
    file_path = os.path.join(directory, base_filename + ".txt")
    
    if genres:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(", ".join(genres))
        print(f"Genres saved to: {file_path}")
    else:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("unknown")
        print(f"No search results found, saved 'unknown' to: {file_path}")

async def fetch(session, url):
    """Fetch a URL asynchronously."""
    async with session.get(url) as response:
        return await response.text()

async def search_goodreads_and_extract_genres(query_data):
    """Search Goodreads for a book and extract its genres if the book has enough ratings."""
    original_filename, sanitized_filename, directory = query_data
    base_url = "https://www.goodreads.com/search?q="
    encoded_query = urllib.parse.quote_plus(sanitized_filename)
    search_url = base_url + encoded_query

    async with aiohttp.ClientSession() as session:
        search_page = await fetch(session, search_url)
        soup = BeautifulSoup(search_page, "lxml", parse_only=SoupStrainer("tr", {"itemscope": "", "itemtype": "http://schema.org/Book"}))

        first_result = soup.find("tr", {"itemscope": "", "itemtype": "http://schema.org/Book"})

        if not first_result:
            print(f"No search results found for query: {sanitized_filename}")
            save_genres_to_file(original_filename, None, directory)
            return

        ratings_count = extract_ratings_from_search_page(first_result)

        if ratings_count < 500:
            print(f"Skipping '{sanitized_filename}' as it has less than 500 ratings.")
            save_genres_to_file(original_filename, ["unpopular"], directory)
            return

        book_link = first_result.find("a", class_="bookTitle")
        if not book_link or not book_link["href"]:
            print(f"Book link not found in the first result for query: {sanitized_filename}")
            save_genres_to_file(original_filename, None, directory)
            return

        book_url = "https://www.goodreads.com" + book_link["href"]
        print(f"Book URL: {book_url}")

        book_page = await fetch(session, book_url)
        genres = extract_genres_from_goodreads(book_page)

        if genres:
            save_genres_to_file(original_filename, genres, directory)
        else:
            save_genres_to_file(original_filename, None, directory)

def extract_ratings_from_search_page(result):
    """Extract the number of ratings from the search page result."""
    ratings_span = result.find("span", class_="greyText smallText uitext")
    if ratings_span:
        minirating = ratings_span.find("span", class_="minirating")
        if minirating:
            ratings_text = minirating.text.split("—")[-1].strip()
            ratings_count_str = ratings_text.split()[0].replace(",", "")
            try:
                ratings_count = int(ratings_count_str)
                return ratings_count
            except ValueError:
                print("Error parsing ratings count.")
                return 0
    return 0

def extract_genres_from_goodreads(page_content):
    """Extract genres from a Goodreads book page content."""
    soup = BeautifulSoup(page_content, 'lxml', parse_only=SoupStrainer('span', class_='BookPageMetadataSection__genreButton'))

    # Find all genre buttons directly
    genres = [
        label.get_text()
        for button in soup.select('span.BookPageMetadataSection__genreButton')
        if (label := button.select_one('span.Button__labelItem'))
    ]

    return genres

def process_folder(directory):
    """Process a folder, prompting for each new folder."""
    filenames = [f for f in os.listdir(directory) if f.endswith(".epub")]

    # Filter out files that already have an associated .txt file
    filenames = [f for f in filenames if not os.path.exists(os.path.join(directory, os.path.splitext(f)[0] + ".txt"))]

    for i in range(0, len(filenames), 15):  # Process in batches of 15
        batch = filenames[i:i + 15]
        with ThreadPoolExecutor(max_workers=15) as executor:
            results = list(executor.map(process_single_file, batch, [directory] * len(batch)))
            # Ensure that the results are converted into a list before passing to asyncio.gather
            asyncio.run(gather_tasks(results))

async def gather_tasks(results):
    """Run the search_goodreads_and_extract_genres tasks concurrently."""
    await asyncio.gather(*[search_goodreads_and_extract_genres(result) for result in results])

from concurrent.futures import ThreadPoolExecutor
import threading

class GenreFileFilterApp:
    def __init__(self, root):
        # Initialization code (same as before)
        self.root = root
        self.root.title("EPUB Genre Filter")
        self.root.geometry("800x600")
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.directory = ""
        self.genres = {}
        self.selected_genre = None
        self.genre_buttons = {}
        self.create_widgets()

    def create_widgets(self):
        # UI components definitions (same as before)
        self.paned_window = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.paned_window.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.genre_frame = tk.Frame(self.paned_window, width=200)
        self.genre_frame.pack_propagate(False)
        self.paned_window.add(self.genre_frame, weight=1)

        self.search_frame = tk.Frame(self.genre_frame)
        self.search_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.search_entry = tk.Entry(self.search_frame)
        self.search_entry.pack(fill=tk.X)
        self.search_entry.bind('<KeyRelease>', self.filter_genres)

        self.genre_canvas = tk.Canvas(self.genre_frame, width=180)
        self.genre_scrollbar = ttk.Scrollbar(self.genre_frame, orient=tk.VERTICAL, command=self.genre_canvas.yview)
        
        self.genre_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5,0))
        self.genre_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.genre_canvas.configure(yscrollcommand=self.genre_scrollbar.set)
        self.genre_inner_frame = tk.Frame(self.genre_canvas)
        self.genre_canvas.create_window((0, 0), window=self.genre_inner_frame, anchor="nw", width=180)

        self.genre_inner_frame.bind("<Configure>", lambda e: self.genre_canvas.configure(
            scrollregion=self.genre_canvas.bbox("all")))
        self.genre_canvas.bind("<Enter>", lambda e: self._bind_mouse_scroll(self.genre_canvas))
        self.genre_canvas.bind("<Leave>", lambda e: self._unbind_mouse_scroll(self.genre_canvas))

        self.epub_frame = tk.Frame(self.paned_window)
        self.paned_window.add(self.epub_frame, weight=3)

        self.epub_listbox = tk.Listbox(self.epub_frame, height=20)
        self.epub_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.epub_scrollbar = tk.Scrollbar(self.epub_frame, orient=tk.VERTICAL, command=self.epub_listbox.yview)
        self.epub_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.epub_listbox.config(yscrollcommand=self.epub_scrollbar.set)

        self.folder_frame = tk.Frame(self.root)
        self.folder_frame.pack(padx=10, pady=5, fill=tk.X)

        self.browse_button = tk.Button(self.folder_frame, text="Browse", command=self.browse_folder)
        self.browse_button.grid(row=0, column=0, padx=(0, 5))

        self.folder_entry = tk.Entry(self.folder_frame, width=50)
        self.folder_entry.grid(row=0, column=1, padx=(5, 0), sticky="ew")
        self.folder_frame.columnconfigure(1, weight=1)

        self.button_frame = tk.Frame(self.root)
        self.button_frame.pack(padx=10, pady=5, fill=tk.X)

        self.update_button = tk.Button(self.button_frame, text="Update", command=self.update_content)
        self.update_button.grid(row=0, column=0, padx=5, pady=5)

        self.move_button = tk.Button(self.button_frame, text="Move Selected Genre Books", command=self.move_books)
        self.move_button.grid(row=0, column=1, padx=5, pady=5)

        self.delete_button = tk.Button(self.button_frame, text="Delete Selected Genre Books", command=self.delete_books)
        self.delete_button.grid(row=0, column=2, padx=5, pady=5)

        self.status_label = tk.Label(self.root, text="Ready", anchor="e", relief=tk.SUNKEN)
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

    def _bind_mouse_scroll(self, widget):
        widget.bind_all("<MouseWheel>", lambda e: self._on_mousewheel(e, widget))

    def _unbind_mouse_scroll(self, widget):
        widget.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event, widget):
        widget.yview_scroll(int(-1*(event.delta/120)), "units")

    def browse_folder(self):
        folder_path = filedialog.askdirectory()
        if folder_path:
            self.directory = folder_path
            self.folder_entry.delete(0, tk.END)
            self.folder_entry.insert(0, folder_path)
            self.status_label.config(text="Ready")  # Reset status label
            threading.Thread(target=self.process_folder, args=(self.directory,)).start()

    def update_content(self):
        if not self.directory:
            messagebox.showerror("Error", "Please select a folder first.")
            return

        self.genres = {}
        self.selected_genre = None
        self.epub_listbox.delete(0, tk.END)
        
        for button in self.genre_buttons.values():
            button.destroy()
        self.genre_buttons.clear()

        txt_files = [f for f in os.listdir(self.directory) if f.endswith(".txt")]
        epub_files = {f.replace(".epub", ""): f for f in os.listdir(self.directory) if f.endswith(".epub")}

        genre_frequency = {}

        for txt_file in txt_files:
            txt_path = os.path.join(self.directory, txt_file)
            book_name = os.path.splitext(txt_file)[0]

            with open(txt_path, "r", encoding="utf-8") as file:
                genres = file.read().strip().split(",")
                genres = {genre.strip().lower() for genre in genres if genre.strip()}

            if genres:
                self.genres[book_name] = genres
                for genre in genres:
                    genre_frequency[genre] = genre_frequency.get(genre, 0) + 1

        sorted_genres = sorted(genre_frequency.items(), key=lambda x: (-x[1], x[0]))

        for genre, freq in sorted_genres:
            var = tk.IntVar()
            button = tk.Checkbutton(
                self.genre_inner_frame, 
                text=f"{genre} ({freq})", 
                variable=var,
                command=lambda g=genre: self.on_genre_toggle(g)
            )
            button.var = var
            button.pack(anchor="w", padx=5, pady=2)
            self.genre_buttons[genre] = button

        self.genre_inner_frame.update_idletasks()
        self.genre_canvas.configure(scrollregion=self.genre_canvas.bbox("all"))

        self.filter_epub_files()

    def on_genre_toggle(self, genre):
        if self.selected_genre == genre:
            self.selected_genre = None
        else:
            self.selected_genre = genre

        for g, button in self.genre_buttons.items():
            if g != genre:
                button.var.set(0)

        self.filter_epub_files()

    def filter_epub_files(self):
        self.epub_listbox.delete(0, tk.END)

        if self.selected_genre:
            for book_name, genres in self.genres.items():
                if self.selected_genre in genres:
                    epub_file = f"{book_name}.epub"
                    self.epub_listbox.insert(tk.END, epub_file)

    def delete_books(self):
        if not self.selected_genre:
            messagebox.showerror("Error", "Please select a genre first.")
            return
        
        confirm = messagebox.askyesno("Confirm Deletion", f"Are you sure you want to delete all books for genre '{self.selected_genre}'?")
        if not confirm:
            return

        files_deleted = 0
        for book_name, genres in self.genres.items():
            if self.selected_genre in genres:
                epub_file = f"{book_name}.epub"
                txt_file = f"{book_name}.txt"
                epub_path = os.path.join(self.directory, epub_file)
                txt_path = os.path.join(self.directory, txt_file)

                if os.path.exists(epub_path):
                    os.remove(epub_path)
                    files_deleted += 1
                if os.path.exists(txt_path):
                    os.remove(txt_path)
                    files_deleted += 1

        self.update_content()

        if files_deleted > 0:
            messagebox.showinfo("Success", f"Deleted {files_deleted} files associated with the genre '{self.selected_genre}'.")
        else:
            messagebox.showwarning("No Files Found", "No files found to delete for the selected genre.")

    def filter_genres(self, event=None):
        search_text = self.search_entry.get().lower()
        
        for genre, button in self.genre_buttons.items():
            if search_text in genre.lower():
                button.pack(anchor="w", padx=5, pady=2)
            else:
                button.pack_forget()
        
        self.genre_inner_frame.update_idletasks()
        self.genre_canvas.configure(scrollregion=self.genre_canvas.bbox("all"))

    def move_books(self):
        if not self.selected_genre:
            messagebox.showerror("Error", "Please select a genre first.")
            return
        
        genre_folder = os.path.join(self.directory, self.selected_genre)
        try:
            os.makedirs(genre_folder, exist_ok=True)
        except Exception as e:
            messagebox.showerror("Error", f"Could not create folder: {str(e)}")
            return
        
        books_to_move = []
        for book_name, genres in self.genres.items():
            if self.selected_genre in genres:
                epub_file = f"{book_name}.epub"
                txt_file = f"{book_name}.txt"
                books_to_move.extend([epub_file, txt_file])
        
        if not books_to_move:
            messagebox.showinfo("Info", "No books found for selected genre.")
            return
        
        confirm = messagebox.askyesno(
            "Confirm Move",
            f"Move {len(books_to_move)} files to folder '{self.selected_genre}'?"
        )
        if not confirm:
            return
        
        moved_count = 0
        errors = []
        for filename in books_to_move:
            src_path = os.path.join(self.directory, filename)
            dst_path = os.path.join(genre_folder, filename)
            
            try:
                if os.path.exists(src_path):
                    base, ext = os.path.splitext(dst_path)
                    counter = 1
                    while os.path.exists(dst_path):
                        dst_path = f"{base}_{counter}{ext}"
                        counter += 1
                    
                    os.rename(src_path, dst_path)
                    moved_count += 1
            except Exception as e:
                errors.append(f"{filename}: {str(e)}")
        
        if errors:
            error_msg = "\n".join(errors)
            messagebox.showerror(
                "Errors Occurred",
                f"Moved {moved_count} files. Errors:\n{error_msg}"
            )
        else:
            messagebox.showinfo(
                "Success",
                f"Successfully moved {moved_count} files to '{self.selected_genre}' folder."
            )
        
        self.update_content()

    def process_folder(self, directory):
        filenames = [f for f in os.listdir(directory) if f.endswith(".epub")]
        filenames = [f for f in filenames if not os.path.exists(os.path.join(directory, os.path.splitext(f)[0] + ".txt"))]
        total_files = len(filenames)
        processed_count = 0

        if total_files == 0:
            self.status_label.config(text="No files to process.")
            return

        for i in range(0, total_files, 15):
            batch = filenames[i:i + 15]
            with ThreadPoolExecutor(max_workers=15) as executor:
                results = list(executor.map(process_single_file, batch, [directory] * len(batch)))
                asyncio.run(gather_tasks(results))
        
            processed_count += len(batch)
            self.status_label.config(text=f"Processing... {processed_count}/{total_files}")
            self.root.update_idletasks()  # Force UI update
            self.update_content()  # Update the UI dynamically

        self.status_label.config(text="Ready")


if __name__ == "__main__":
    root = tk.Tk()
    app = GenreFileFilterApp(root)
    root.mainloop()