"""Adds VGMdb search support to Beets
"""
from beets.autotag.hooks import AlbumInfo, TrackInfo
from beets.plugins import BeetsPlugin, get_distance
import logging
import requests
import re

log = logging.getLogger("beets")


class VGMdbPlugin(BeetsPlugin):
    def __init__(self):
        super(VGMdbPlugin, self).__init__()
        self.config.add(
            {
                "source_weight": 0.0,
                "lang-priority": "ja, en, ja-latn, Japanese, Romaji, English",
            }
        )
        log.debug("Querying VGMdb")
        self.source_weight = self.config["source_weight"].as_number()
        self.lang = self.config["lang-priority"].get().split(",")

    def album_distance(self, items, album_info, mapping):
        """Returns the album distance.
        """
        return get_distance(
            data_source='vgmdb',
            info=album_info,
            config=self.config
        )

    def track_distance(self, item, track_info):
        """Returns the track distance.
        """
        return get_distance(
            data_source='vgmdb',
            info=track_info,
            config=self.config
        )

    def candidates(self, items, artist, album, va_likely, extra_tags=None):
        """Returns a list of AlbumInfo objects for VGMdb search results
        matching an album and artist (if not various).
        """
        if va_likely:
            query = album
        else:
            query = "{} {}".format(artist, album)
        try:
            return self.get_albums(query, va_likely)
        except:
            log.exception("VGMdb Search Error: (query: {})".format(query))
            return []

    def album_for_id(self, album_id):
        """Fetches an album by its VGMdb ID and returns an AlbumInfo object
        or None if the album is not found.
        """
        log.debug("Querying VGMdb for release {}".format(album_id))

        # Get from VGMdb
        r = requests.get("https://vgmdb.info/album/{}?format=json".format(album_id))

        # Decode Response's content
        try:
            item = r.json()
        except ValueError:
            log.debug("VGMdb JSON Decode Error: (id: {})".format(album_id))
            return None

        return self.get_album_info(item, False)

    def get_albums(self, query, va_likely):
        """Returns a list of AlbumInfo objects for a VGMdb search query."""
        # Strip non-word characters from query. Things like "!" and "-" can
        # cause a query to return no results, even if they match the artist or
        # album title. Use `re.UNICODE` flag to avoid stripping non-english
        # word characters.
        query = re.sub(r"(?u)\W+", " ", query)
        # Strip medium information from query, Things like "CD1" and "disk 1"
        # can also negate an otherwise positive result.
        query = re.sub(r"(?i)\b(CD|disc|disk)\s*\d+", "", query)

        # Query VGMdb
        r = requests.get("http://vgmdb.info/search/albums/{}?format=json".format(query))
        albums = []

        # Decode Response's content
        try:
            items = r.json()
        except:
            log.debug("VGMdb JSON Decode Error: (query: {})".format(query))
            return albums

        # Break up and get search results
        for item in items["results"]["albums"]:
            album_id = str(item["link"][6:])
            albums.append(self.album_for_id(album_id))
            if len(albums) >= 5:
                break
        log.debug("get_albums Querying VGMdb for release {}".format(query))
        return albums

    def get_album_info(self, item, va_likely):
        """Convert json data into a format beets can read"""

        # If a preferred lang is available use that instead
        album_name = item["name"]
        for lang in self.lang:
            if lang in item["names"]:
                album_name = item["names"][lang]
                break

        album_id = item["link"][6:]
        country = "JP"
        catalognum = item["catalog"]

        # Get Artist information
        #if "performers" in item and len(item["performers"]) > 0:
        #    artist_type = "performers"
        #else:
        artist_type = "composers" # i prefer composers, uncomment the above if you want that functionality

        artists = []
        for artist in item[artist_type]:
            for lang in self.lang:
                if lang in artist["names"]:
                    artists.append(artist["names"][lang])
                    break

        artist = artists[0]
        if "link" in item[artist_type][0]:
            artist_id = item[artist_type][0]["link"][7:]
        else:
            artist_id = None


        # Get Track metadata
        Tracks = []
        total_index = 0
        for disc_index, disc in enumerate(item["discs"]):
            for track_index, track in enumerate(disc["tracks"]):
                total_index += 1

                
                title = list(track["names"].values())[0]

                for lang in self.lang:
                    if lang in track["names"]:
                        title = track["names"][lang]
                        break

                index = total_index

                if track["track_length"] == "Unknown":
                    length = 0
                else:
                    length = track["track_length"].split(":")
                    length = (float(length[0]) * 60) + float(length[1])

                media = item["media_format"]
                medium = disc_index
                medium_index = track_index
                new_track = TrackInfo(
                    title=title,
                    track_id=int(index),
                    length=float(length),
                    index=int(index),
                    medium=int(medium),
                    medium_index=int(medium_index),
                    medium_total=item["discs"].count,
                )
                Tracks.append(new_track)

        # Format Album release date
        if item["release_date"]:
            release_date = item["release_date"].split("-")
            year = release_date[0]
            month = release_date[1]
            day = release_date[2]
        else:
            year = "0000"
            month = "00"
            day = "00"

        for lang in self.lang:
            if lang in item["publisher"]["names"]:
                label = item["publisher"]["names"][lang]

                mediums = len(item["discs"])
                media = item["media_format"]

                data_url = item["vgmdb_link"]

                return AlbumInfo(
                    album=album_name,
                    album_id=str(album_id),
                    artist=artist,
                    artist_id=str(artist_id),
                    tracks=Tracks,
                    asin=None,
                    albumtype=None,
                    va=False,
                    year=int(year),
                    month=int(month),
                    day=int(day),
                    original_year=year,
                    original_month=month,
                    original_day=day,
                    label=label,
                    mediums=int(mediums),
                    media=str(media),
                    data_source="VGMdb",
                    data_url=str(data_url),
                    country=str(country),
                    catalognum=str(catalognum),
                )
