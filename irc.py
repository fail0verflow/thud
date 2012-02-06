
# Numeric response codes
# Source: http://libircclient.sourceforge.net/group__rfcnumbers.html

RFC_RPL_WELCOME     = 001
RFC_RPL_YOURHOST    = 002
RFC_RPL_CREATED     = 003
RFC_RPL_MYINFO      = 004
RFC_RPL_BOUNCE      = 005

RFC_RPL_USERHOST    = 302
RFC_RPL_ISON        = 303
RFC_RPL_AWAY        = 301
RFC_RPL_UNAWAY      = 305
RFC_RPL_NOWAWAY     = 306

RFC_RPL_WHOISUSER   = 311
RFC_RPL_WHOISSERVER = 312
RFC_RPL_WHOISOPERATOR    = 313
RFC_RPL_WHOISIDLE   = 317
RFC_RPL_ENDOFWHOIS  = 318
RFC_RPL_WHOISCHANNELS = 319
RFC_RPL_WHOWASUSER  = 314
RFC_RPL_ENDOFWHOWAS = 369

RFC_RPL_LIST        = 322
RFC_RPL_LISTEND     = 323

RFC_RPL_UNIQOPIS    = 325

RFC_RPL_CHANNELMODEIS = 324
RFC_RPL_NOTOPIC     = 331
RFC_RPL_TOPIC       = 332
RFC_RPL_INVITING    = 341
RFC_RPL_SUMMONING   = 342
RFC_RPL_INVITELIST  = 346
RFC_RPL_ENDOFINVITELIST = 347
RFC_RPL_EXCEPTLIST  = 348
RFC_RPL_ENDOFEXCEPTLIST = 349

RFC_RPL_VERSION     = 351
RFC_RPL_WHOREPLY    = 352
RFC_RPL_ENDOFWHO    = 315

RFC_RPL_NAMEREPLY   = 353
RFC_RPL_ENDOFNAMES  = 366
RFC_RPL_LINKS       = 364
RFC_RPL_ENDOFLINKS  = 365
RFC_RPL_BANLIST     = 367
RFC_RPL_ENDOFBANLIST    = 368
RFC_RPL_INFO        = 371
RFC_RPL_ENDOFINFO   = 374

RFC_RPL_MOTDSTART   = 375
RFC_RPL_MOTD        = 372
RFC_RPL_ENDOFMOTD   = 376

RFC_RPL_YOUREOPER   = 381
RFC_RPL_REHASHING   = 382
RFC_RPL_YOURSERVICE = 383
RFC_RPL_TIME        = 391
RFC_RPL_USERSTART   = 392
RFC_RPL_USERS       = 393
RFC_RPL_ENDOFUSERS  = 394
RFC_RPL_NOUSERS     = 395
RFC_RPL_TRACELINK   = 200
RFC_RPL_TRACECONNECTING = 201
RFC_RPL_TRACEHANDSHAKE = 202
RFC_RPL_TRACEUNKNOWN = 203
RFC_RPL_TRACEOPERATOR = 204
RFC_RPL_TRACEUSER   = 205
RFC_RPL_TRACESERVER = 206
RFC_RPL_TRACESERVICE = 207
RFC_RPL_TRACENEWTYPE = 208
RFC_RPL_TRACECLASS  = 209
RFC_RPL_TRACELOG    = 261
RFC_RPL_TRACEEND    = 262
RFC_RPL_STATSLINKINFO = 211
RFC_RPL_STATSCOMMANDS = 212
RFC_RPL_ENDOFSTATS  = 219
RFC_RPL_STATSUPTIME = 242
RFC_RPL_STATSOLINE  = 243
RFS_RPL_UMODEIS     = 221
RFC_RPL_SERGVLIST   = 234
RFC_RPL_SERVLISTEND = 235
RFC_RPL_LUSERCLIENT = 251
RFC_RPL_LUSEROP     = 252
RFC_RPL_LUSERUNKNOWN = 253
RFC_RPL_LUSERCHANNELS = 254
RFC_RPL_LUSERME     = 255
RFC_RPL_LADMINME    = 256
RFC_RPL_ADMINLOC1   = 257
RFC_RPL_ADMINLOC2   = 258
RFC_RPL_ADMINEMAIL  = 259
RFC_RPL_TRYAGAIN    = 263

RFC_ERR_NOSUCHNICK      = 401
RFC_ERR_NOSUCHSERVER    = 402
RFC_ERR_NOSUCHCHANNEL   = 403
RFC_ERR_CANNOTSENDTOCHAN= 404
RFC_ERR_TOOMANYCHANNELS = 405
RFC_ERR_WASNOSUCHNICK   = 406
RFC_ERR_TOOMANYTARGETS  = 407
RFC_ERR_NOSUCHSERVICE   = 408
RFC_ERR_NOORIGIN        = 409
RFC_ERR_NORECIPIENT     = 411
RFC_ERR_NOTEXTTOSEND    = 412
RFC_ERR_NOTOPLEVEL      = 413
RFC_ERR_WILDTOPLEVEL    = 414
RFC_ERR_BADMASK         = 415
RFC_ERR_UNKNOWNCOMMAND  = 421
RFC_ERR_NOMOTD          = 422
RFC_ERR_NOADMININFO     = 423
RFC_ERR_FILEERROR       = 424
RFC_ERR_NONICKNAMEGIVEN = 431
RFC_ERR_ERRONEUSNICKNAME= 432
RFC_ERR_NICKNAMEINUSE   = 433
RFC_ERR_NICKCOLLISION   = 436
RFC_ERR_UNAVAILRESOURCE = 437
RFC_ERR_USERNOTINCHANNEL= 441
RFC_ERR_NOTONCHANNEL    = 442
RFC_ERR_USERONCHANNEL   = 443
RFC_ERR_NOLOGIN         = 444
RFC_ERR_SUMMONDISABLED  = 445
RFC_ERR_USERSDISABLED   = 446
RFC_ERR_NOTREGISTERED   = 451
RFC_ERR_NEEDMOREPARAMS  = 461
RFC_ERR_ALREADYREGISTERED=462
RFC_ERR_NOPERMFORHOST   = 463
RFC_ERR_PASSWDMISMATCH  = 464
RFC_ERR_YOUREBANNEDCREEP= 465
RFC_ERR_YOUWILLBEBANNED = 466
RFC_ERR_KEYSET          = 467
RFC_ERR_CHANNELISFULL   = 471
RFC_ERR_UNKNOWNMODE     = 472
RCF_ERR_INVITEONLYCHAN  = 473
RCF_ERR_BANNEDFROMCHAN  = 474
RFC_ERR_BADCHANNELKEY    = 475
RFC_ERR_BADCHANMASK     = 476
RFC_ERR_NOCHANMODES     = 477
RFC_ERR_BANLISTFULL     = 478
RFC_ERR_NOPRIVELEGES    = 481
RFC_ERR_CHANOPRIVSNEEDED= 482
RFC_ERR_CANTKILLSERVER  = 483
RFC_ERR_RESTRICTED      = 484
RFC_ERR_UNIQOPPRIVSNEEDED=485
RFC_ERR_NOOPERHOST      = 491
RFC_ERR_UMODEUNKNOWNFLAG= 501
RFC_ERR_USERSDONTMATCH  = 502