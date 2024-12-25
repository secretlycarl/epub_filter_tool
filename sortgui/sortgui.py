import os
import tkinter as tk
from tkinter import filedialog
from tkinter import messagebox
from tkinter import ttk

class GenreFileFilterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("EPUB Genre Filter")
        self.root.geometry("800x600")

        # Initialize variables
        self.directory = ""
        self.genres = {}
        self.selected_genre = None  # Only one genre can be selected
        self.genre_buttons = {}  # Initialize genre buttons

        # UI components
        self.create_widgets()

    def create_widgets(self):
        # Paned window for splitting genre and EPUB files areas
        self.paned_window = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.paned_window.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Genre filter section (Left column)
        self.genre_frame = tk.Frame(self.paned_window, width=200)  # Fixed width for genre section
        self.genre_frame.pack_propagate(False)  # Prevent the frame from resizing with content
        self.paned_window.add(self.genre_frame, weight=1)

        # Add search bar for genres above genre list
        self.search_frame = tk.Frame(self.genre_frame)
        self.search_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.search_entry = tk.Entry(self.search_frame)
        self.search_entry.pack(fill=tk.X)
        self.search_entry.bind('<KeyRelease>', self.filter_genres)

        # Create canvas with scrollbar
        self.genre_canvas = tk.Canvas(self.genre_frame, width=180)
        self.genre_scrollbar = ttk.Scrollbar(self.genre_frame, orient=tk.VERTICAL, command=self.genre_canvas.yview)
        
        # Pack the canvas and scrollbar
        self.genre_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5,0))
        self.genre_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Configure the canvas
        self.genre_canvas.configure(yscrollcommand=self.genre_scrollbar.set)
        self.genre_inner_frame = tk.Frame(self.genre_canvas)
        self.genre_canvas.create_window((0, 0), window=self.genre_inner_frame, anchor="nw", width=180)

        # Bind events for better scrolling
        self.genre_inner_frame.bind("<Configure>", lambda e: self.genre_canvas.configure(
            scrollregion=self.genre_canvas.bbox("all")))
        self.genre_canvas.bind("<Enter>", lambda e: self._bind_mouse_scroll(self.genre_canvas))
        self.genre_canvas.bind("<Leave>", lambda e: self._unbind_mouse_scroll(self.genre_canvas))

        # Display matching epub files (Center section)
        self.epub_frame = tk.Frame(self.paned_window)
        self.paned_window.add(self.epub_frame, weight=3)

        self.epub_listbox = tk.Listbox(self.epub_frame, height=20)
        self.epub_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.epub_scrollbar = tk.Scrollbar(self.epub_frame, orient=tk.VERTICAL, command=self.epub_listbox.yview)
        self.epub_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.epub_listbox.config(yscrollcommand=self.epub_scrollbar.set)

        # Folder input section
        self.folder_label = tk.Label(self.root, text="Select Folder:")
        self.folder_label.pack(padx=10, pady=5)

        self.folder_entry = tk.Entry(self.root, width=50)
        self.folder_entry.pack(padx=10, pady=5)

        self.browse_button = tk.Button(self.root, text="Browse", command=self.browse_folder)
        self.browse_button.pack(padx=10, pady=5)

        # Update button to refresh the content
        self.update_button = tk.Button(self.root, text="Update", command=self.update_content)
        self.update_button.pack(padx=10, pady=5)

        # Delete button to delete books of the selected genre
        self.delete_button = tk.Button(self.root, text="Delete Selected Genre Books", command=self.delete_books)
        self.delete_button.pack(padx=10, pady=5)

        # Add move button below epub listbox
        self.move_button = tk.Button(self.root, text="Move Selected Genre Books", command=self.move_books)
        self.move_button.pack(padx=10, pady=5)

    def _bind_mouse_scroll(self, widget):
        """Bind mouse wheel to scroll only when mouse is over the widget"""
        widget.bind_all("<MouseWheel>", lambda e: self._on_mousewheel(e, widget))

    def _unbind_mouse_scroll(self, widget):
        """Unbind mouse wheel when mouse leaves the widget"""
        widget.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event, widget):
        """Handle mouse wheel scrolling"""
        widget.yview_scroll(int(-1*(event.delta/120)), "units")

    def browse_folder(self):
        """Allow the user to browse for a folder."""
        folder_path = filedialog.askdirectory()
        if folder_path:
            self.directory = folder_path
            self.folder_entry.delete(0, tk.END)
            self.folder_entry.insert(0, folder_path)
            self.update_content()

    def update_content(self):
        """Update the genres and EPUB files based on the selected folder."""
        if not self.directory:
            messagebox.showerror("Error", "Please select a folder first.")
            return

        # Initialize the genres and matching EPUB files
        self.genres = {}
        self.selected_genre = None
        self.epub_listbox.delete(0, tk.END)
        
        # Clear existing genre checkbuttons
        for button in self.genre_buttons.values():
            button.destroy()
        self.genre_buttons.clear()

        # Get all .txt and .epub files in the directory
        txt_files = [f for f in os.listdir(self.directory) if f.endswith(".txt")]
        epub_files = {f.replace(".epub", ""): f for f in os.listdir(self.directory) if f.endswith(".epub")}

        # Track genre frequency
        genre_frequency = {}

        # First pass: count genre frequencies
        for txt_file in txt_files:
            txt_path = os.path.join(self.directory, txt_file)
            book_name = os.path.splitext(txt_file)[0]

            with open(txt_path, "r", encoding="utf-8") as file:
                genres = file.read().strip().split(",")
                genres = {genre.strip().lower() for genre in genres if genre.strip()}

            if genres:
                self.genres[book_name] = genres
                # Count frequency of each genre
                for genre in genres:
                    genre_frequency[genre] = genre_frequency.get(genre, 0) + 1

        # Sort genres by frequency
        sorted_genres = sorted(genre_frequency.items(), key=lambda x: (-x[1], x[0]))

        # Create buttons in order of frequency
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

        # Update the scrollregion after adding all buttons
        self.genre_inner_frame.update_idletasks()
        self.genre_canvas.configure(scrollregion=self.genre_canvas.bbox("all"))

        # Filter EPUB files based on selected genre
        self.filter_epub_files()

    def on_genre_toggle(self, genre):
        """Handles the genre toggle action, ensuring only one genre is selected at a time."""
        if self.selected_genre == genre:
            self.selected_genre = None
        else:
            self.selected_genre = genre

        # Update the genre checkbuttons (uncheck all others)
        for g, button in self.genre_buttons.items():
            if g != genre:
                button.var.set(0)

        # Filter EPUB files based on selected genre
        self.filter_epub_files()

    def filter_epub_files(self):
        """Filter EPUB files based on the selected genre."""
        self.epub_listbox.delete(0, tk.END)

        if self.selected_genre:
            # Filter based on selected genre
            for book_name, genres in self.genres.items():
                if self.selected_genre in genres:
                    epub_file = f"{book_name}.epub"
                    self.epub_listbox.insert(tk.END, epub_file)

    def delete_books(self):
        """Delete all books and their associated txt files for the selected genre."""
        if not self.selected_genre:
            messagebox.showerror("Error", "Please select a genre first.")
            return
        
        # Ask for confirmation before deletion
        confirm = messagebox.askyesno("Confirm Deletion", f"Are you sure you want to delete all books for genre '{self.selected_genre}'?")
        if not confirm:
            return

        # Delete associated .epub and .txt files
        files_deleted = 0
        for book_name, genres in self.genres.items():
            if self.selected_genre in genres:
                epub_file = f"{book_name}.epub"
                txt_file = f"{book_name}.txt"
                epub_path = os.path.join(self.directory, epub_file)
                txt_path = os.path.join(self.directory, txt_file)

                # Check if files exist and delete
                if os.path.exists(epub_path):
                    os.remove(epub_path)
                    files_deleted += 1
                if os.path.exists(txt_path):
                    os.remove(txt_path)
                    files_deleted += 1

        # Refresh the content after deletion
        self.update_content()

        # Show a message with the result
        if files_deleted > 0:
            messagebox.showinfo("Success", f"Deleted {files_deleted} files associated with the genre '{self.selected_genre}'.")
        else:
            messagebox.showwarning("No Files Found", "No files found to delete for the selected genre.")

    def filter_genres(self, event=None):
        """Filter genres based on search text"""
        search_text = self.search_entry.get().lower()
        
        # Show/hide buttons based on search
        for genre, button in self.genre_buttons.items():
            if search_text in genre.lower():
                button.pack(anchor="w", padx=5, pady=2)
            else:
                button.pack_forget()
        
        # Update the scrollregion
        self.genre_inner_frame.update_idletasks()
        self.genre_canvas.configure(scrollregion=self.genre_canvas.bbox("all"))

    def move_books(self):
        """Move all books of selected genre to a new folder"""
        if not self.selected_genre:
            messagebox.showerror("Error", "Please select a genre first.")
            return
        
        # Create genre folder if it doesn't exist
        genre_folder = os.path.join(self.directory, self.selected_genre)
        try:
            os.makedirs(genre_folder, exist_ok=True)
        except Exception as e:
            messagebox.showerror("Error", f"Could not create folder: {str(e)}")
            return
        
        # Get list of books to move
        books_to_move = []
        for book_name, genres in self.genres.items():
            if self.selected_genre in genres:
                epub_file = f"{book_name}.epub"
                txt_file = f"{book_name}.txt"
                books_to_move.extend([epub_file, txt_file])
        
        if not books_to_move:
            messagebox.showinfo("Info", "No books found for selected genre.")
            return
        
        # Confirm before moving
        confirm = messagebox.askyesno(
            "Confirm Move",
            f"Move {len(books_to_move)} files to folder '{self.selected_genre}'?"
        )
        if not confirm:
            return
        
        # Move the files
        moved_count = 0
        errors = []
        for filename in books_to_move:
            src_path = os.path.join(self.directory, filename)
            dst_path = os.path.join(genre_folder, filename)
            
            try:
                if os.path.exists(src_path):
                    # If file already exists in destination, add a number
                    base, ext = os.path.splitext(dst_path)
                    counter = 1
                    while os.path.exists(dst_path):
                        dst_path = f"{base}_{counter}{ext}"
                        counter += 1
                    
                    os.rename(src_path, dst_path)
                    moved_count += 1
            except Exception as e:
                errors.append(f"{filename}: {str(e)}")
        
        # Show results
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
        
        # Refresh the display
        self.update_content()

if __name__ == "__main__":
    root = tk.Tk()
    app = GenreFileFilterApp(root)
    root.mainloop()
