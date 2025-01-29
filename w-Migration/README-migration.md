This folder contains the state files from various gdcopy operations used in migrating from shared folders to google's shared drives in the Northlake Google Workspace.

The state files provide:
* `src2dest {}`: A dictionary of original source file information such as name and modification dates, along with the destination file ID where the file ended up. This can be useful for tracking down migration issues, locating the original location in a shared folder for a file that may have been moved or modified on the shared drive after the migration.
* `shortcuts_to_copy [ [shortcutid, new_parent_folder], ... ]`: Lists all shortcuts and the parent folder to which they are being copied. This is used in the copy process after copying is completed to create shortcuts in the destination folder. It is needed as a post-copying step because a shortcut may refer to a file that has not yet been copied. Since copying can take place incrementally, we need to maintain where all shortcuts referred and create the new shortcuts later so they can refer to the new location of files.

Various migrations have taken place, and the different gdcopy files represent data from those migrations.

**WARNING**: While these gdcopy files ideally would be integrated into a single state file, it is possible that some contain migrations that were reverted and started over. In this case, we would have duplicate `src2dest` entries which would need to be resolved, likely by using the file modification date of the `src2dest` files. It is likely that the solution is to integrate the gdcopy state files in order from oldest to newest.

The .log files contain processing logs from different migrations.  They also include google drive file ids and could be useful in reconstructing or troubleshooting issues with files post migration.

**RETENTION** These can likely be removed a couple of years after the migrations.  
