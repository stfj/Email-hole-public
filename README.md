Email Hole.

For years I have had a terrible relationship with email. It arrives in floods. It's like 99% people trying to sell me shit or automated services telling me words and 1% really extremely important stuff.

About a year ago I had an idea for how to create a new email service centered around the 'Email hole'.

About a week ago I realized I didn't actually need to create an email service, or even an email client! I could just create a little python script that logs into my email through SMTP and organizes things for me. I've spent the evenings since then pulling it together with the help of a LLM (sorry the code is soooo bad. I barely know python and I certainly don't know how to handle email stuff. I'm pretty blown away it was able to get me this far!)

=-=-=-=-=-=-=-=-=-=-=-=-=
How does email hole work?

1. Every email that comes into my inbox that isn't from someone I have corresponded with in the past goes to a folder called The Hole.
2. Emails that go to The Hole are first checked with a LLM to see if they're receipts, or interview requests, or whatever other "smart" rules you dream up with.
3. Emails that have been in The Hole for longer than a week are move to a folder called 'The Void' that I never check.

That's it! It's awesome. My inbox is all stuff I actually care about, and sometimes I check The Hole. I don't even have to flag important stuff anymore because so few emails actually land in my real inbox.

The AI rules don't work super great, but maybe you can make them work better? Or maybe they'll work better in the future when these beasts get smarter.. At least it's all using local AI stuff through GPT-4-all so nothing ever leaves my computer.

=-=-=-=-=-=-=-=-=-=-=-=-=
How do I set this up?

1. configure the config.cfg file with your information

2. configure the rules yaml however you want

3. setup all the required folders on your mail client

4. put a bunch of test emails in the processing folder and confirm everything works

6. setup a few rules on your email client (I use fastmail).
- Any special email you truly need to see but never need to reply to should be sorted to your inbox (like for example, anything coming from @docusign in my caase)
- All the rest of your email that comes in should go to a folder called AI/AI-Processing

7. configure a cronjob to run the script, and then forget about it! welcome to email nirvanasortof.