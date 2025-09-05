# 🏏 Cricket Player Auction App

A customizable cricket player auction app built using Python and Streamlit. Ideal for managing team selection and bidding during local or fantasy cricket tournaments.

## Updates
 ### UI
 - added frame for player photos in auction tab as well as team summary
 - enhanced UI with a pinch of css
 ### PLAYER MANAGEMENT
 - input player data is stored in a database file ```auction.db``` with this format

    | player_id     | full_name     | department    | year          | role          | photo(drive/optional) | auctioned |
    | ------------- | ------------- | ------------- | ------------- | ------------- | --------------------- | --------- |

 - output player summary is stored in separate xlsx files for sold and unsold players which can be downloaded from the summary tab 
 - to reset auction go to the sidebar menu
 - player **photos** must be stored in the folder ```/Cricket-Auction-App/photos``` in the following format ```photo_{(player_id)-1}.jpg``` 
    - example: for player_id 1 the file name should be photo_0.jpg
    - if you use google form for player registration use ```drive.py``` script to store the photos locally by passing the excel file as ```input.xlsx```


## HOW TO USE
- setup ```auction.db``` and **photos** folder as mentioned above
- change directory to Cricket-Auction-App:
```
cd ./Cricket-Auction-App
```
- run with Streamlit
```
 Streamlit run auctionApp.py
```






