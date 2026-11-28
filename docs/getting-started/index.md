# Tutorial: Your First Saved Page

This tutorial takes you from nothing to finding a page by describing it. It uses the hosted MemoryLane at **[memorylane.site](https://memorylane.site)**, so you only need Chrome (or another Chromium browser). It takes about ten minutes.

You will:

1. create an account and install the extension,
2. save a page by hand,
3. find it by meaning, by exact words, and by site and time,
4. read a summary, delete a page and undo it,
5. turn on automatic capture safely.

Once you're done, the [Usage Guide](../user-guide/automatic-capture.md) covers every feature in detail.

## 1. Create an account

Open [memorylane.site](https://memorylane.site) and press **Get started**. Sign up with Google, or with an email address and a password.

**You should see** the home page with a search box and the message that your library is empty. Each account has its own private library; nobody else can see or search it.

## 2. Install the extension

1. Open [memorylane.site/extension](https://memorylane.site/extension) and download `memorylane-extension.zip`. Unzip it.
2. Go to `chrome://extensions` and turn on **Developer mode** (top right).
3. Click **Load unpacked** and choose the unzipped folder.
4. Pin MemoryLane to the toolbar (the puzzle-piece menu), open it and press **Sign in**. Use the same account as on the website.

**You should see** the popup with the current page and a **Remember this page** button.

## 3. Save your first page

Open any article you'd like to keep. For this tutorial, use the Wikipedia article on [photosynthesis](https://en.wikipedia.org/wiki/Photosynthesis).

Open the extension and press **Remember this page**.

**You should see** "Saved just now" with an **Undo** button. MemoryLane has extracted the article's text (without menus and footers), split it into passages and indexed them, **in your browser**: by default pages are kept on your device, encrypted, and the server never receives them. The first save downloads the search model once (about 130 MB) and takes a little longer. Back on the website, the page appears under **Recently saved**, marked *on this device*.

(To keep pages on the server instead, so you can search them from your phone, open the extension's **Settings**. [Storage and Backups](../user-guide/storage.md) explains the choice.)

Save two or three more pages on different topics, so the next steps have something to choose between.

## 4. Find it by meaning

On the website, type a description that does **not** use the article's title:

```text
how plants turn sunlight into energy
```

**You should see** the photosynthesis article first, with a snippet: the two or three sentences that best match your description, with the matching words highlighted. MemoryLane matched the idea, not the wording.

## 5. Find it by exact words

Now search for a precise term from the article:

```text
Calvin cycle
```

Exact names, codes and rare words are found by keyword search, which runs alongside the search by meaning. A page that holds the words you typed is kept even when its meaning is only loosely related.

## 6. Say where or when

If you remember the site or the time, add it:

```text
wikipedia article i saved today
```

**You should see** your Wikipedia pages from today ranked first. Site names come from the sites you've saved from, and times can be words like *yesterday*, *last week* or *in march*. These are hints: a better match from another site still shows up. See [Searching](../user-guide/search.md#saying-where-or-when).

## 7. Read a summary

Hover over a result (or select it with the arrow keys) and press **Summarise**, or press `S`.

**You should see** a short summary of that page, written for your query. Summaries are made only when you ask, and only that page is sent to the summary model.

## 8. Delete a page, and undo it

Open the account menu (your initial, top right) and choose **All saved pages**. Hover over a page and press the bin icon.

**You should see** the page disappear and a toast saying "Page deleted · Undo". Press **Undo** within six seconds and the page comes back. Otherwise it's deleted for good. Closing or reloading the tab in those six seconds still deletes it.

## 9. Turn on automatic capture

In the extension popup, switch on **Auto-capture** at the bottom. The first time, the popup explains what it does; confirm to turn it on.

From now on, MemoryLane saves pages you actually **read**: on screen for 30 seconds, or scrolled halfway through. It only saves pages that look like content, such as articles, documentation, posts and videos. It never saves email, banking, social media, private apps, login or payment pages.

To try it, read an article for half a minute and open the popup.

**You should see** it under **Auto-saved today**, with **Remove** and **Never this site**. To keep a site out for good, use **Excluded sites** in the popup. See [What automatic capture skips](../user-guide/automatic-capture.md#what-automatic-capture-skips).

## What you've learned

- Saving is one click, and automatic capture keeps only what you read.
- You find pages by describing them. Exact words, sites and times help but aren't needed.
- Everything you save is private to your account and can be deleted at any time.

## Next steps

- [Usage Guide](../user-guide/automatic-capture.md): every feature in detail, including keyboard shortcuts, YouTube videos and voice search.
- [Privacy](../privacy.md): what is stored and what leaves the server.
- [Installation](../development/installation.md): run your own copy instead of the hosted one.
