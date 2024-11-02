from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
import time
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from video_downloader import VideoDownloader
import json
import os
import requests

class MasterDownloader:
    def __init__(self):
        self.console = Console()
        self.video_downloader = VideoDownloader()
        self.setup_chrome_options()
        
    def setup_chrome_options(self):
        self.chrome_options = Options()
        self.chrome_options.add_argument('--headless')
        self.chrome_options.add_argument('--disable-gpu')
        self.chrome_options.add_argument('--no-sandbox')
        self.chrome_options.add_argument('--disable-dev-shm-usage')
        self.chrome_options.add_argument('--log-level=3')
        self.chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])

    def get_course_options(self, driver):
        try:
            # Wait for course select to be present
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "Course"))
            )
            course_select = Select(driver.find_element(By.ID, "Course"))
            options = []
            for option in course_select.options[1:]:  # Skip the "All Course" option
                options.append({
                    'value': option.get_attribute('value'),
                    'text': option.text
                })
            return options
        except Exception as e:
            self.console.print(f"[red]Error getting course options: {str(e)}[/red]")
            return []

    def get_class_links(self, driver):
        try:
            # Wait for class boxes to load
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".uu-routine-box"))
            )
            time.sleep(2)  # Additional wait for dynamic content
            
            class_boxes = driver.find_elements(By.CSS_SELECTOR, ".uu-routine-box .displayClass")
            links = []
            
            for box in class_boxes:
                try:
                    video_link = box.find_element(By.CSS_SELECTOR, "a[href*='ClassDetails']").get_attribute('href')
                    title = box.find_element(By.CSS_SELECTOR, ".uu-routine-title").text.strip()
                    topic = box.find_element(By.CSS_SELECTOR, ".uu-latex-body-style").text.strip()
                    
                    # Check if notes are available
                    has_notes = len(box.find_elements(By.CSS_SELECTOR, "a[href*='isNotes=true']")) > 0
                    
                    links.append({
                        'url': video_link,
                        'title': title,
                        'topic': topic,
                        'has_notes': has_notes
                    })
                except Exception as e:
                    self.console.print(f"[yellow]Warning: Skipped a class due to error: {str(e)}[/yellow]")
                    continue
                    
            return links
        except Exception as e:
            self.console.print(f"[red]Error getting class links: {str(e)}[/red]")
            return []

    def process_single_class(self, cookies_string, class_info):
        try:
            self.console.print(f"\n[yellow]Processing: {class_info['title']}[/yellow]")
            
            # Initialize driver for this class
            driver = webdriver.Chrome(options=self.chrome_options)
            driver.get("https://online.utkorsho.tech")
            
            # Add cookies
            cookies_dict = self.video_downloader.get_cookies_dict(cookies_string)
            for name, value in cookies_dict.items():
                driver.add_cookie({'name': name, 'value': value})
            
            # Load class page
            driver.get(class_info['url'])
            time.sleep(2)
            
            # Switch to video tab first
            self.video_downloader.switch_to_tab(driver, "video")
            time.sleep(2)
            
            # Get video sources
            video_sources = self.video_downloader.get_video_sources(driver, cookies_dict)
            
            if not video_sources:
                # Try alternative method
                video_url = self.video_downloader.get_video_url(cookies_string, class_info['url'])
                if video_url:
                    video_sources = [('direct', video_url, '720')]
            
            if video_sources:
                # Extract YouTube ID if available
                youtube_id = None
                for source in video_sources:
                    if source[0] == 'youtube':
                        youtube_id = source[1]
                        break
                
                # Handle YouTube option if available
                if youtube_id and self.video_downloader.ask_youtube_preference(youtube_id):
                    filename = os.path.join(
                        self.video_downloader.config['download_path'],
                        f"{class_info['title']}_youtube.mp4"
                    )
                    if not self.video_downloader.download_youtube(youtube_id, filename):
                        self.console.print("[yellow]Falling back to direct download...[/yellow]")
                        # Process direct video sources
                        if video_sources:
                            self.video_downloader.process_direct_sources(video_sources, class_info['title'], cookies_string)
                else:
                    # Process direct video sources
                    if video_sources:
                        self.video_downloader.process_direct_sources(video_sources, class_info['title'], cookies_string)
            
            # Handle notes download if available
            if class_info['has_notes']:
                self.video_downloader.switch_to_tab(driver, "note")
                time.sleep(2)
                
                note_url = self.video_downloader.get_note_url_from_link(driver)
                if note_url:
                    note_filename = os.path.join(
                        self.video_downloader.config['download_path'],
                        f"{class_info['title']}_note.pdf"
                    )
                    self.video_downloader.download_note(note_url, cookies_string, note_filename)
            
            return True
                
        except Exception as e:
            self.console.print(f"[red]Error processing class: {str(e)}[/red]")
            return False
        finally:
            if 'driver' in locals():
                driver.quit()

    def download_classes(self, cookies_string):
        driver = webdriver.Chrome(options=self.chrome_options)
        try:
            # Load the page with nice UI
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=self.console
            ) as progress:
                task = progress.add_task("[cyan]Loading page...", total=100)
                
                # Load initial page
                driver.get("https://online.utkorsho.tech/Routine/PastClasses")
                progress.update(task, completed=30)
                
                # Add cookies
                cookies_dict = self.video_downloader.get_cookies_dict(cookies_string)
                for name, value in cookies_dict.items():
                    driver.add_cookie({'name': name, 'value': value})
                progress.update(task, completed=60)
                
                # Reload with cookies
                driver.get("https://online.utkorsho.tech/Routine/PastClasses")
                time.sleep(3)
                progress.update(task, completed=100)
            
            # Get and display courses in a nice box
            courses = self.get_course_options(driver)
            if not courses:
                self.console.print("\n[red]╭── Error ───╮[/red]")
                self.console.print("[red]│ Failed to get courses. Please try again.[/red]")
                self.console.print("[red]╰────────────╯[/red]")
                return
                
            self.console.print("\n[yellow]╭─── Available Courses ───╮[/yellow]")
            for i, course in enumerate(courses, 1):
                self.console.print(f"[cyan]│ {i}. {course['text']}[/cyan]")
            self.console.print("[yellow]╰──────────────────────╯[/yellow]")
            
            course_choice = int(Prompt.ask("\n[bold blue]Choose course number[/bold blue]")) - 1
            selected_course = courses[course_choice]
            
            # Select course with progress
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=self.console
            ) as progress:
                task = progress.add_task("[cyan]Loading course...", total=100)
                
                course_select = Select(driver.find_element(By.ID, "Course"))
                course_select.select_by_value(selected_course['value'])
                progress.update(task, completed=50)
                time.sleep(2)
                progress.update(task, completed=100)
            
            # Get subjects with progress
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=self.console
            ) as progress:
                task = progress.add_task("[cyan]Loading subjects...", total=100)
                
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.ID, "Subject"))
                )
                progress.update(task, completed=50)
                
                subject_select = Select(driver.find_element(By.ID, "Subject"))
                subjects = []
                for option in subject_select.options:
                    subjects.append({
                        'value': option.get_attribute('value') or "-1",
                        'text': option.text
                    })
                progress.update(task, completed=100)
            
            # Display subjects in a nice box
            self.console.print("\n[yellow]╭─── Available Subjects ───╮[/yellow]")
            for i, subject in enumerate(subjects, 1):
                self.console.print(f"[cyan]│ {i}. {subject['text']}[/cyan]")
            self.console.print("[yellow]╰──────────────────────╯[/yellow]")
            
            subject_choice = int(Prompt.ask("\n[bold blue]Choose subject number[/bold blue]")) - 1
            selected_subject = subjects[subject_choice]
            
            # Select subject and load classes with progress
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=self.console
            ) as progress:
                task = progress.add_task("[cyan]Loading classes...", total=100)
                
                subject_select.select_by_value(selected_subject['value'])
                progress.update(task, completed=30)
                time.sleep(2)
                
                # Get class links with retry
                max_retries = 3
                class_links = []
                for attempt in range(max_retries):
                    progress.update(task, completed=30 + ((attempt + 1) * 20))
                    class_links = self.get_class_links(driver)
                    if class_links:
                        break
                    time.sleep(1)
                
                progress.update(task, completed=100)
            
            if not class_links:
                self.console.print("\n[red]╭─── Error ───╮[/red]")
                self.console.print("[red]│ No classes found![/red]")
                self.console.print("[red]╰──���─────────╯[/red]")
                return
                
            self.console.print(f"\n[green]Found {len(class_links)} classes[/green]")
            
            # Display classes in a nice box
            self.console.print("\n[yellow]╭─── Available Classes ───╮[/yellow]")
            for i, class_info in enumerate(class_links, 1):
                self.console.print(f"[cyan]│ {i}. {class_info['title']}[/cyan]")
                self.console.print(f"[cyan]│    {class_info['topic']}[/cyan]")
                if class_info['has_notes']:
                    self.console.print("[green]│    📝 Notes available[/green]")
                else:
                    self.console.print("[red]│    ❌ No notes[/red]")
                if i < len(class_links):
                    self.console.print("[yellow]│[/yellow]")
            self.console.print("[yellow]╰────────────────────╯[/yellow]")
            
            choice = Prompt.ask(
                "\n[bold blue]Enter class numbers to download (comma-separated, or 'all')[/bold blue]"
            )
            
            selected_links = []
            if choice.lower() == 'all':
                selected_links = class_links
            else:
                try:
                    indices = [int(x.strip()) - 1 for x in choice.split(',')]
                    selected_links = [class_links[i] for i in indices]
                except:
                    self.console.print("\n[red]╭─── Error ───╮[/red]")
                    self.console.print("[red]│ Invalid input![/red]")
                    self.console.print("[red]╰────────────╯[/red]")
                    return
            
            # Download files with nice progress
            if selected_links:
                # Get preferences from first file
                first_class = selected_links[0]
                use_youtube = False
                youtube_quality = None
                direct_quality = None
                
                # Initialize temp driver for getting preferences
                temp_driver = webdriver.Chrome(options=self.chrome_options)
                try:
                    temp_driver.get("https://online.utkorsho.tech")
                    for name, value in cookies_dict.items():
                        temp_driver.add_cookie({'name': name, 'value': value})
                        
                    temp_driver.get(first_class['url'])
                    time.sleep(2)
                    
                    self.video_downloader.switch_to_tab(temp_driver, "video")
                    time.sleep(2)
                    
                    video_sources = self.video_downloader.get_video_sources(temp_driver, cookies_dict)
                    
                    if video_sources:
                        # Check for YouTube
                        youtube_id = None
                        for source in video_sources:
                            if source[0] == 'youtube':
                                youtube_id = source[1]
                                break
                        
                        if youtube_id:
                            use_youtube = self.video_downloader.ask_youtube_preference(youtube_id)
                            if use_youtube:
                                youtube_quality = self.video_downloader.get_youtube_quality_preference(youtube_id)
                        
                        if not use_youtube:
                            # Get direct download quality
                            direct_sources = [s for s in video_sources if s[0] == 'direct']
                            if direct_sources:
                                resolutions = sorted([int(s[2]) for s in direct_sources], reverse=True)
                                direct_quality = self.video_downloader.ask_resolution_preference(resolutions)[0]
                finally:
                    temp_driver.quit()
                
                # Download all files with same preferences
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                    TextColumn("•"),
                    TextColumn("[cyan]{task.fields[speed]}[/cyan]"),
                    console=self.console
                ) as progress:
                    main_task = progress.add_task(
                        "[bold cyan]Overall progress...", 
                        total=len(selected_links),
                        speed="0/0 files"
                    )
                    
                    for i, class_info in enumerate(selected_links, 1):
                        progress.update(
                            main_task, 
                            speed=f"{i}/{len(selected_links)} files"
                        )
                        
                        # Add newline before processing each file
                        self.console.print("")
                        self.console.print(f"[yellow]Processing: {class_info['title']}[/yellow]")
                        
                        if self.video_downloader.process_class_page_with_preferences(
                            cookies_string, 
                            class_info['url'],
                            use_youtube=use_youtube,
                            youtube_quality=youtube_quality,
                            direct_quality=direct_quality
                        ):
                            self.console.print(f"[green]✓ Successfully downloaded {class_info['title']}[/green]")
                        else:
                            self.console.print(f"[red]✗ Failed to download {class_info['title']}[/red]")
                        
                        progress.advance(main_task)
                
                self.console.print("\n[bold green]╭─── Success ───╮[/bold green]")
                self.console.print("[bold green]│ All downloads completed![/bold green]")
                self.console.print("[bold green]╰─────────────╯[/bold green]")
                
        except Exception as e:
            self.console.print("\n[red]╭─── Error ───╮[/red]")
            self.console.print(f"[red]│ {str(e)}[/red]")
            self.console.print("[red]╰────────────╯[/red]")
        finally:
            driver.quit()

def main():
    downloader = MasterDownloader()
    
    # Try to load saved cookies
    cookies = downloader.video_downloader.load_cookies()
    if not cookies:
        cookies = downloader.console.input("\n[bold blue]🔑 Enter your cookies string:[/bold blue] ").strip()
        if cookies:
            downloader.video_downloader.save_cookies(cookies)
    else:
        downloader.console.print("\n[bold green]✅ Using saved cookies[/bold green]")
        if downloader.console.input("[bold blue]🔄 Update cookies? (y/N):[/bold blue] ").strip().lower() == 'y':
            cookies = downloader.console.input("[bold blue]🔑 Enter new cookies:[/bold blue] ").strip()
            if cookies:
                downloader.video_downloader.save_cookies(cookies)
    
    while True:
        downloader.download_classes(cookies)
        if not Confirm.ask("\n[bold blue]Download more classes?[/bold blue]"):
            break
    
    downloader.console.print("\n[bold yellow]👋 Thank you for using Udvash Video Downloader![/bold yellow]")

if __name__ == "__main__":
    main()
